// ====== Code Summary ======
// Derives the provider-availability verdict for a collection's Overview health board. The verdict is
// a PURE projection of the LIVE probe (`GET .../health`) — "can this collection reach its providers
// and index right now" — and nothing else: past job/document failures are a separate concern owned
// by the Jobs tab, deliberately kept OUT of this board so the header answers exactly one question.
// An unresolved probe (still loading, or the check itself failed) must never claim "Operational" —
// that silent fallback is the false-confidence bug this endpoint was built to close.

import type { CollectionHealth, ProviderHealth } from "../../api/collections";
import type { ChipTone } from "../../components/Chip";

/** One rendered verdict — a tone for the headline Chip, its label, and one line of detail. */
export interface HealthVerdict {
  tone: ChipTone;
  label: string;
  detail: string;
}

/** The first provider (ingest or search side) reporting a hard reachability/auth failure. */
function firstFailingProvider(health: CollectionHealth): ProviderHealth | undefined {
  return [...health.ingest.providers, ...health.search.providers].find(
    (p) => p.status === "unreachable" || p.status === "auth_failed",
  );
}

/** One human line naming what a failing/degraded provider or blob is, for the banner detail. */
function describeProbeIssue(health: CollectionHealth): string {
  if (health.ingest.build_error) return `Ingestion pipeline is invalid: ${health.ingest.build_error}`;
  if (health.search.build_error) return `Search pipeline is invalid: ${health.search.build_error}`;

  const bad = firstFailingProvider(health);
  if (bad) {
    const reason = bad.status === "auth_failed" ? "rejected its credentials" : "is unreachable";
    return `${bad.kind} (${bad.node_id}) ${reason}${bad.detail ? ` — ${bad.detail}` : ""}.`;
  }
  if (health.search.index.vector_count === 0) return "The index holds 0 chunks — nothing is searchable yet.";
  return "See the provider breakdown below for details.";
}


/**
 * Project the live provider probe onto the board's headline verdict — provider availability ONLY.
 *
 * Priority (most severe wins): an unresolved probe → "Health unknown" (a failed check) or "Checking…"
 * (still loading), never "Operational"; probe `down` → Down (red); probe `degraded` → Degraded
 * (amber); probe `operational` → Operational (green). Past job/document failures are intentionally
 * NOT considered here — they are surfaced by the Jobs tab, not this board.
 *
 * @param health - The live provider probe, or null while it hasn't resolved yet (loading, or the
 *   check itself failed) — never treated as "operational" by default.
 * @param healthError - Set when the probe fetch itself failed, distinct from a probe that ran and
 *   reported `down`/`degraded`.
 * @returns The verdict to render in the health board header.
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

  // 2. A critical provider is unreachable/auth-failed, or a pipeline blob won't build.
  if (health.verdict === "down") {
    return { tone: "error", label: "Down", detail: describeProbeIssue(health) };
  }

  // 3. A non-critical provider is down, or the index holds nothing yet.
  if (health.verdict === "degraded") {
    return { tone: "warn", label: "Degraded", detail: describeProbeIssue(health) };
  }

  // 4. Every probed provider answered.
  return { tone: "ok", label: "Operational", detail: "All providers reachable." };
}
