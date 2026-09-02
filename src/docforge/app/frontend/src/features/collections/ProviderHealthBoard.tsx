// ====== Code Summary ======
// The Overview's hero — a provider board grouped by pipeline side (Ingest / Search), one row per
// provider node that has an endpoint concept, probed live via GET .../health. Pure-local steps
// (`status: "skipped"`, no endpoint) are hidden behind a footnote so the board reads as "everything
// that talks to the outside world", not the full ingestion graph. Probes automatically on mount
// (the parent wires that) and again on every "Re-check" click; a failed re-check keeps the
// last-known board on screen instead of blanking it. The row detail (headers + Ingest/Search rows)
// sits behind a collapsed-by-default "Provider status (N)" disclosure — the headline Chip + reason
// line already answer "is it healthy", the per-node table is the drill-down, not the first read.
//
// ONE locus of "loading" status — the header Chip ("Checking…") — not three: the Re-check button
// keeps its static label (just disabled while probing) and the unresolved-probe banner is
// suppressed in favour of a skeleton in the body, so a fresh mount never repeats "Checking…"/
// "Probing providers…" across the button, a banner AND the body all at once.

import type { CollectionHealth, ProviderHealth } from "../../api/collections";
import { Button } from "../../components/Button";
import { Chip } from "../../components/Chip";
import type { Navigate } from "../../shell/view";
import { theme as t } from "../../theme";
import type { HealthFixTarget, HealthVerdict } from "./collectionHealth";
import { ProviderHealthRow, ProviderHealthTableHeader } from "./ProviderHealthRow";
import { humanizeRelativeTime } from "./relativeTime";

interface ProviderHealthBoardProps {
  health: CollectionHealth | null;
  verdict: HealthVerdict;
  loading: boolean;
  error: string | null;
  onRecheck: () => void;
  /** Where the verdict's actual cause can be repaired — null when nothing is actionable (the
   *  "operational" state, or a genuinely empty collection whose fix is the Overview's own upload hero). */
  fixTarget: HealthFixTarget | null;
  onNavigate: Navigate;
}

/**
 * Drop full-content duplicate rows and stamp each survivor with a render-stable key.
 *
 * A React `key` built only from `side:node_id` collides when the graph assigns the same id to two
 * DISTINCT nodes (an upstream id-generation gap, not something this board can fix) — that would
 * either lose a row or repaint one twice. Two rows that are byte-identical across every field ARE a
 * true duplicate (the same leaf reported twice) and get collapsed to one; two rows that merely share
 * an id but differ elsewhere are real, distinct nodes and both render, disambiguated by their index.
 *
 * @param providers - One side's raw provider rows, in server order.
 * @returns The deduplicated rows, each paired with a key unique within this render.
 */
function dedupeAndKeyProviders(providers: ProviderHealth[]): { key: string; provider: ProviderHealth }[] {
  const seenSignatures = new Set<string>();
  const kept: { key: string; provider: ProviderHealth }[] = [];
  providers.forEach((p, index) => {
    const signature = `${p.side}:${p.node_id}:${p.kind}:${p.family}:${p.status}:${p.endpoint}:${p.detail}:${p.latency_ms}`;
    if (seenSignatures.has(signature)) return;
    seenSignatures.add(signature);
    kept.push({ key: `${p.side}:${p.node_id}:${index}`, provider: p });
  });
  return kept;
}

/** A quiet 3-bar placeholder for the board body while the probe is in flight — a distinct visual
 *  (not a repeat of the header Chip's "Checking…" text) so a fresh mount reads as "working", not
 *  as the same status line printed three times. */
function HealthBoardSkeleton() {
  const widths = [70, 45, 58];
  return (
    <div style={{ padding: `${t.space.m}px ${t.space.l}px`, display: "flex", flexDirection: "column", gap: t.space.s }}>
      {widths.map((w, i) => (
        <div
          key={i}
          style={{
            height: 13, width: `${w}%`, borderRadius: t.radius.s, background: t.color.surface2,
            animation: "df-pulse 1.4s ease-in-out infinite", animationDelay: `${i * 0.15}s`,
          }}
        />
      ))}
      <style>
        {"@keyframes df-pulse { 0%, 100% { opacity: 0.45; } 50% { opacity: 1; } } "
          + "@media (prefers-reduced-motion: reduce) { [style*=\"df-pulse\"] { animation: none !important; } }"}
      </style>
    </div>
  );
}

/** One side's group — a section caption plus its endpoint-bearing rows, or nothing when every step
 *  on that side is purely local. */
function StageGroup({ title, providers }: { title: string; providers: ProviderHealth[] }) {
  const rows = dedupeAndKeyProviders(providers.filter((p) => p.status !== "skipped"));
  if (rows.length === 0) return null;
  return (
    <div>
      <div
        style={{
          color: t.color.mute, fontSize: t.font.size.xs, fontWeight: t.font.weight.bold,
          textTransform: "uppercase", letterSpacing: "0.08em", padding: `${t.space.s}px ${t.space.l}px`,
          background: t.color.surface2,
        }}
      >
        {title}
      </div>
      {rows.map(({ key, provider }) => <ProviderHealthRow key={key} provider={provider} />)}
    </div>
  );
}

export function ProviderHealthBoard({ health, verdict, loading, error, onRecheck, fixTarget, onNavigate }: ProviderHealthBoardProps) {
  const allProviders = health ? [...health.ingest.providers, ...health.search.providers] : [];
  const skippedCount = allProviders.filter((p) => p.status === "skipped").length;
  const visibleCount = allProviders.length - skippedCount;

  return (
    <div
      style={{
        background: t.color.surface, border: `1px solid ${t.color.line}`, borderRadius: t.radius.l,
        boxShadow: t.shadow.sm, marginBottom: t.space.l, overflow: "hidden",
      }}
    >
      <div
        style={{
          display: "flex", alignItems: "center", gap: t.space.m,
          padding: `${t.space.m}px ${t.space.l}px`, borderBottom: `1px solid ${t.color.line}`,
        }}
      >
        <span style={{ fontFamily: t.font.display, fontWeight: t.font.weight.bold, fontSize: t.font.size.xl, color: t.color.text }}>
          Collection health
        </span>
        <Chip tone={verdict.tone}>{verdict.label}</Chip>
        <div style={{ marginLeft: "auto", display: "flex", alignItems: "center", gap: t.space.m }}>
          {health && (
            <span style={{ color: t.color.mute, fontSize: t.font.size.xs }}>
              checked <span style={{ fontFamily: t.font.mono }}>{humanizeRelativeTime(health.checked_at)}</span>
            </span>
          )}
          {/* Steel, not orange — Re-check is a routine re-probe, not the screen's one accent action;
              brand.md reserves forge orange for the single primary thing (here, "Fix" the actual
              fault, or the Overview's own Upload hero). Static label — "Checking…" already has its
              one locus in the header Chip above, disabled state alone conveys "in flight". */}
          <Button size="sm" variant="secondary" onClick={onRecheck} disabled={loading}>
            Re-check
          </Button>
        </div>
      </div>

      {/* Names WHY right under the header for every RESOLVED verdict but the calm "Operational" one —
          including the NEUTRAL "empty" state (styled quietly, not as an alarm) so a brand-new
          collection reads as "ready to ingest" rather than an unexplained non-green chip. Gated on
          `health !== null || error` so the unresolved-probe placeholder ("Checking…"/"Probing
          providers…") never ALSO prints here — the header Chip is its one locus, the body below is
          its skeleton. */}
      {verdict.tone !== "ok" && verdict.detail && (health !== null || error) && (
        <div
          style={{
            display: "flex", alignItems: "center", gap: t.space.m,
            padding: `${t.space.s}px ${t.space.l}px`, borderBottom: `1px solid ${t.color.line}`,
            background: verdict.tone === "error" ? t.color.errorSoft : verdict.tone === "warn" ? t.color.warnSoft : t.color.surface2,
            color: verdict.tone === "error" ? t.color.error : verdict.tone === "warn" ? t.color.warn : t.color.dim,
            fontSize: t.font.size.m,
          }}
        >
          <span style={{ flex: 1 }}>{verdict.detail}</span>
          {fixTarget && (
            <Button size="sm" variant="primary" onClick={() => onNavigate(fixTarget.view)}>
              {fixTarget.label} →
            </Button>
          )}
        </div>
      )}

      {!health ? (
        error ? (
          <div style={{ padding: t.space.l, color: t.color.dim, fontSize: t.font.size.m }}>Could not verify — {error}</div>
        ) : loading ? (
          <HealthBoardSkeleton />
        ) : (
          <div style={{ padding: t.space.l, color: t.color.dim, fontSize: t.font.size.m }}>Not yet checked.</div>
        )
      ) : visibleCount === 0 ? (
        skippedCount > 0 && (
          <div style={{ padding: `${t.space.s}px ${t.space.l}px`, color: t.color.mute, fontSize: t.font.size.xs }}>
            +{skippedCount} local step{skippedCount === 1 ? "" : "s"} (no endpoint)
          </div>
        )
      ) : (
        <details>
          <summary
            style={{
              cursor: "pointer", userSelect: "none", listStyle: "none",
              padding: `${t.space.s}px ${t.space.l}px`, borderBottom: `1px solid ${t.color.line}`,
              color: t.color.dim, fontSize: t.font.size.m, fontWeight: t.font.weight.semibold,
              display: "flex", alignItems: "center", gap: t.space.s,
            }}
          >
            <span className="df-chev" style={{ color: t.color.mute, fontSize: t.font.size.s }}>▶</span>
            Provider status ({visibleCount})
          </summary>
          <ProviderHealthTableHeader />
          <StageGroup title="Ingest" providers={health.ingest.providers} />
          <StageGroup title="Search" providers={health.search.providers} />
          {skippedCount > 0 && (
            <div style={{ padding: `${t.space.s}px ${t.space.l}px`, color: t.color.mute, fontSize: t.font.size.xs }}>
              +{skippedCount} local step{skippedCount === 1 ? "" : "s"} (no endpoint)
            </div>
          )}
          {error && (
            <div
              style={{
                padding: `${t.space.s}px ${t.space.l}px`, borderTop: `1px dashed ${t.color.line}`,
                color: t.color.warn, fontSize: t.font.size.xs,
              }}
            >
              Last re-check failed — {error}. Showing the previous result.
            </div>
          )}
        </details>
      )}
    </div>
  );
}
