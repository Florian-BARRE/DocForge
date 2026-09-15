// ====== Code Summary ======
// Overview cockpit panel — the collections whose live health probe reads down/degraded/ingest
// unavailable, each row linking straight into that collection. A LINK-through glance (capped rows),
// never a duplicate of the full Collections grid; "View all in Collections" routes to the same
// "attention" preset the Overview's own tile already links to.

import type { CollectionHealth } from "../../api/collections";
import type { ChipTone } from "../../components/Chip";
import { Chip } from "../../components/Chip";
import type { Navigate } from "../../shell/view";
import { theme } from "../../theme";
import { needsAttention } from "./CollectionsStatusTiles";
import { useCollectionsFleet, type FleetEntry } from "../collections/state/useCollectionsFleet";

const MAX_ROWS = 6;

// Local, deliberately minimal — a full verdict→tone/label/detail projection already exists in
// features/collections/collectionHealth.ts, but feature slices don't cross-import small pure
// helpers (agent-memory/frontend/feature_slice_isolation.md); this panel only ever renders the
// non-operational verdicts anyway, so it needs the label, not the whole health-board vocabulary.
const TONE_BY_VERDICT: Record<CollectionHealth["verdict"], ChipTone> = {
  down: "error", degraded: "warn", ingest_unavailable: "warn", empty: "dim", operational: "ok",
};
const LABEL_BY_VERDICT: Record<CollectionHealth["verdict"], string> = {
  down: "Down", degraded: "Degraded", ingest_unavailable: "Ingest unavailable", empty: "Empty", operational: "Operational",
};

interface NeedsAttentionRowProps {
  entry: FleetEntry;
  onNavigate: Navigate;
}

function NeedsAttentionRow({ entry, onNavigate }: NeedsAttentionRowProps) {
  const verdict = entry.health!.verdict;
  const go = () => onNavigate({ name: "collection", collectionId: entry.collection.id });
  return (
    <div
      role="button"
      tabIndex={0}
      onClick={go}
      onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); go(); } }}
      style={{
        display: "flex", flexDirection: "column", gap: 2, padding: `${theme.space.xs}px ${theme.space.s}px`,
        borderRadius: theme.radius.m, cursor: "pointer",
      }}
    >
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: theme.space.s }}>
        <span style={{ color: theme.color.text, fontSize: theme.font.size.s, fontWeight: theme.font.weight.semibold }}>
          {entry.collection.name}
        </span>
        <Chip tone={TONE_BY_VERDICT[verdict]}>{LABEL_BY_VERDICT[verdict]}</Chip>
      </div>
      <span style={{ color: theme.color.mute, fontSize: theme.font.size.xs }}>{entry.health!.reason}</span>
    </div>
  );
}

interface NeedsAttentionPanelProps {
  onNavigate: Navigate;
}

export function NeedsAttentionPanel({ onNavigate }: NeedsAttentionPanelProps) {
  const { collections, visibleEntries } = useCollectionsFleet("all");
  const rows = visibleEntries.filter(needsAttention).slice(0, MAX_ROWS);

  return (
    <div
      style={{
        flex: 1, minWidth: 320, border: `1px solid ${theme.color.line}`, borderRadius: theme.radius.l,
        background: theme.color.surface, padding: theme.space.l, display: "flex", flexDirection: "column", gap: theme.space.s,
      }}
    >
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
        <span style={{ fontFamily: theme.font.display, fontWeight: theme.font.weight.bold, fontSize: theme.font.size.l, color: theme.color.text }}>
          Needs attention
        </span>
        <button
          type="button"
          onClick={() => onNavigate({ name: "collections", health: "attention" })}
          style={{ background: "none", border: "none", padding: 0, cursor: "pointer", color: theme.color.accentSafe, fontSize: theme.font.size.xs, textDecoration: "underline" }}
        >
          View all in Collections
        </button>
      </div>

      {!collections ? (
        <span style={{ color: theme.color.mute, fontSize: theme.font.size.s }}>Probing fleet health…</span>
      ) : rows.length === 0 ? (
        <span style={{ color: theme.color.okStrong, fontSize: theme.font.size.s }}>All collections operational.</span>
      ) : (
        rows.map((entry) => <NeedsAttentionRow key={entry.collection.id} entry={entry} onNavigate={onNavigate} />)
      )}
    </div>
  );
}
