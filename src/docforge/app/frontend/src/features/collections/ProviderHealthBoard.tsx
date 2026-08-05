// ====== Code Summary ======
// The Overview's hero — a provider board grouped by pipeline side (Ingest / Search), one row per
// provider node that has an endpoint concept, probed live via GET .../health. Pure-local steps
// (`status: "skipped"`, no endpoint) are hidden behind a footnote so the board reads as "everything
// that talks to the outside world", not the full ingestion graph. Probes automatically on mount
// (the parent wires that) and again on every "Re-check" click; a failed re-check keeps the
// last-known board on screen instead of blanking it.

import type { CollectionHealth, ProviderHealth } from "../../api/collections";
import { Button } from "../../components/Button";
import { Chip } from "../../components/Chip";
import { theme as t } from "../../theme";
import type { HealthVerdict } from "./collectionHealth";
import { ProviderHealthRow } from "./ProviderHealthRow";
import { humanizeRelativeTime } from "./relativeTime";

interface ProviderHealthBoardProps {
  health: CollectionHealth | null;
  verdict: HealthVerdict;
  loading: boolean;
  error: string | null;
  onRecheck: () => void;
}

/** One side's group — a section caption plus its endpoint-bearing rows, or nothing when every step
 *  on that side is purely local. */
function StageGroup({ title, providers }: { title: string; providers: ProviderHealth[] }) {
  const rows = providers.filter((p) => p.status !== "skipped");
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
      {rows.map((p) => <ProviderHealthRow key={`${p.side}:${p.node_id}`} provider={p} />)}
    </div>
  );
}

export function ProviderHealthBoard({ health, verdict, loading, error, onRecheck }: ProviderHealthBoardProps) {
  const allProviders = health ? [...health.ingest.providers, ...health.search.providers] : [];
  const skippedCount = allProviders.filter((p) => p.status === "skipped").length;

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
          <Button size="sm" variant="primary" onClick={onRecheck} disabled={loading}>
            {loading ? "Checking…" : "Re-check"}
          </Button>
        </div>
      </div>

      {/* When the verdict is Down/Degraded, name WHY right under the header — otherwise an
          unbuildable ingest side (whose group renders no rows) would show "Down" with no reason. */}
      {(verdict.tone === "error" || verdict.tone === "warn") && verdict.detail && (
        <div
          style={{
            padding: `${t.space.s}px ${t.space.l}px`, borderBottom: `1px solid ${t.color.line}`,
            background: verdict.tone === "error" ? t.color.errorSoft : t.color.warnSoft,
            color: verdict.tone === "error" ? t.color.error : t.color.warn, fontSize: t.font.size.m,
          }}
        >
          {verdict.detail}
        </div>
      )}

      {!health ? (
        <div style={{ padding: t.space.l, color: t.color.dim, fontSize: t.font.size.m }}>
          {error ? `Could not verify — ${error}` : loading ? "Probing providers…" : "Not yet checked."}
        </div>
      ) : (
        <>
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
        </>
      )}
    </div>
  );
}
