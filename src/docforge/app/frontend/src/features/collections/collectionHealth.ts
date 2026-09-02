// ====== Code Summary ======
// Derives the provider-availability verdict for a collection's health boards (the Overview's board
// AND the fleet cards on the list page) from the LIVE probe (`GET .../health`) — "can this collection
// reach its providers and index right now" — and nothing else: past job/document failures are a
// separate concern owned by the Jobs tab, deliberately kept OUT of this verdict. An unresolved probe
// (still loading, or the check itself failed) must never claim "Operational" — that silent fallback
// is the false-confidence bug this endpoint was built to close. The headline `detail` is ALWAYS the
// backend's own `reason` line (jargon-free by contract) — never a raw engine error re-derived here.

import type { CollectionHealth, ProviderHealth } from "../../api/collections";
import type { ChipTone } from "../../components/Chip";
import type { View } from "../../shell/view";
import { humanizeRelativeTime } from "./relativeTime";

/** One rendered verdict — a tone for the headline Chip, its label, and one line of detail. */
export interface HealthVerdict {
  tone: ChipTone;
  label: string;
  detail: string;
}

// `empty` is a NEUTRAL state (nothing indexed yet, not a fault) — `dim` tone, never `warn`, so a
// brand-new or still-ingesting collection never reads as alarming.
const TONE_BY_VERDICT: Record<CollectionHealth["verdict"], ChipTone> = {
  operational: "ok",
  empty: "dim",
  degraded: "warn",
  ingest_unavailable: "warn",
  down: "error",
};

const LABEL_BY_VERDICT: Record<CollectionHealth["verdict"], string> = {
  operational: "Operational",
  empty: "Empty",
  degraded: "Degraded",
  ingest_unavailable: "Ingest unavailable",
  down: "Down",
};

/**
 * Project the live provider probe onto a verdict — provider availability ONLY.
 *
 * Priority (most severe wins): an unresolved probe → "Health unknown" (a failed check) or "Checking…"
 * (still loading), never "Operational"; otherwise the backend's own rolled-up `verdict` + `reason`
 * are used verbatim (the roll-up policy — empty/degraded/ingest_unavailable/down precedence — lives
 * server-side in `HealthVerdictResolver`, this is a pure display projection of it).
 *
 * @param health - The live provider probe, or null while it hasn't resolved yet (loading, or the
 *   check itself failed) — never treated as "operational" by default.
 * @param healthError - Set when the probe fetch itself failed, distinct from a probe that ran and
 *   reported a non-operational verdict.
 * @returns The verdict to render in a health board/card.
 */
export function probeVerdict(
  health: CollectionHealth | null,
  healthError: string | null,
): HealthVerdict {
  // 1. The probe hasn't resolved — say so honestly, never assert "Operational" without live proof.
  if (health === null) {
    if (healthError) {
      return { tone: "warn", label: "Health unknown", detail: `Could not verify live provider health — ${healthError}.` };
    }
    return { tone: "dim", label: "Checking…", detail: "Probing providers…" };
  }

  // 2. The backend already resolved the policy — surface its verdict + jargon-free reason as-is.
  return { tone: TONE_BY_VERDICT[health.verdict], label: LABEL_BY_VERDICT[health.verdict], detail: health.reason };
}

/** A "Fix" action for the health board — where the verdict's actual cause can be repaired. */
export interface HealthFixTarget {
  label: string;
  view: View;
}

/**
 * Route an actionable verdict to the editor that can actually repair it — the health board must
 * not just describe a fault, it must point at the fix.
 *
 * The mapping mirrors `HealthVerdictResolver`'s own precedence server-side: `down` means search
 * cannot be served (either the search graph itself is broken, or its query embedder is
 * unreachable/missing — both configured on the Search pipeline tab) ; `ingest_unavailable` means
 * the stored ingest blob is structurally invalid (Ingestion pipeline tab) ; `degraded` names one
 * unreachable provider, routed by the SIDE it sits on (ingest vs search pipeline) exactly like the
 * backend's `__degraded_reason` does. `empty` is only actionable when documents already exist but
 * produced no vectors (a stalled/failed ingest — the Jobs tab is the drill-down) ; on a genuinely
 * empty collection (no documents yet) the Overview's own upload hero IS the fix, so this returns
 * `null` and no redundant button is rendered.
 *
 * @param health - The live provider probe, or null while unresolved (nothing actionable yet).
 * @param collectionId - The collection to deep-link into.
 * @param hasUnindexedDocs - Whether the collection already holds documents despite an `empty`
 *   verdict (0 vectors) — the signal that `empty` here means "stalled", not "nothing uploaded yet".
 * @returns The single most relevant fix action, or null when the verdict is not actionable.
 */
export function healthFixTarget(
  health: CollectionHealth | null,
  collectionId: string,
  hasUnindexedDocs: boolean,
): HealthFixTarget | null {
  if (health === null) return null;

  switch (health.verdict) {
    case "down":
      return health.search.buildable
        ? { label: "Configure query embedder", view: { name: "collection-search-pipeline", collectionId } }
        : { label: "Fix search pipeline", view: { name: "collection-search-pipeline", collectionId } };

    case "ingest_unavailable":
      return { label: "Fix ingestion pipeline", view: { name: "collection-pipeline", collectionId } };

    case "degraded": {
      const down = [...health.ingest.providers, ...health.search.providers].find(
        (p: ProviderHealth) => p.status === "unreachable" || p.status === "auth_failed",
      );
      if (!down) return null;
      return down.side === "ingest"
        ? { label: "Fix ingestion pipeline", view: { name: "collection-pipeline", collectionId } }
        : { label: "Fix search pipeline", view: { name: "collection-search-pipeline", collectionId } };
    }

    case "empty":
      return hasUnindexedDocs ? { label: "Check jobs", view: { name: "collection-jobs", collectionId } } : null;

    default:
      return null;
  }
}

/**
 * The parser provider's kind (e.g. "docling", "pp_structure", "granite_docling") for a fleet card's
 * badge — read straight off the ingest-side sweep, which covers EVERY action leaf (local ones
 * included, reported `skipped`) so a purely in-worker parser still shows up here.
 *
 * @param health - The live provider probe, or null while unresolved.
 * @returns The first ingest-side `parser`-family node's kind, or null when unresolved/absent.
 */
export function parserBadge(health: CollectionHealth | null): string | null {
  return health?.ingest.providers.find((p) => p.family === "parser")?.kind ?? null;
}

/**
 * The fleet card's "Last ingest" metric label.
 *
 * Today the ONLY way a collection can hold indexed content (`vector_count > 0`) while carrying no
 * `last_successful_ingest_at` is a `.dcexport` import — that engine writes chunks straight into
 * Postgres/Qdrant, bypassing the worker's job pipeline entirely (see the collection transfer
 * router), so no `Job` row is ever created to timestamp. A raw "—" in that case reads as broken,
 * not "never happened"; naming the collection's own `created_at` (stamped at import time) as
 * "imported <when>" is honest given today's known code paths. Neither field distinguishes an
 * import from an organic creation directly — flagged to the backend as a gap; an explicit
 * `imported_at`/provenance field on `Collection`/`CollectionHealth` would make this exact.
 *
 * @param health - The live provider probe, or null while unresolved.
 * @param createdAt - The collection's own `created_at`, used only for the import fallback.
 * @returns A relative-time label, an "imported <when>" fallback, or "…"/"—" per the usual rules.
 */
export function lastIngestLabel(health: CollectionHealth | null, createdAt: string | null): string {
  if (!health) return "…";
  const { last_ingest_at, vector_count } = health.search.index;
  if (last_ingest_at) return humanizeRelativeTime(last_ingest_at);
  if (vector_count > 0) return `imported ${humanizeRelativeTime(createdAt)}`;
  return "—";
}
