// ====== Code Summary ======
// One collection summary card in the fleet grid — an operating dashboard row, not a format-chip
// wall: name (lead) + a live health dot/label + doc/chunk counts + last-ingest recency + a parser
// badge, with the supported-format list collapsed to a compact "+N formats" summary. Health, chunk
// count and parser all come from the collection's on-demand `GET .../health` probe (fetched by the
// parent list so every card in the grid can also be sorted/filtered by it); doc count comes from a
// cheap `documents/query` count. Both are fetched independently per card by the parent, so a slow
// probe on one collection never blocks the rest of the grid — this component only renders what it's
// handed, showing "…" while its own slice hasn't resolved yet. An overflow menu in the header row
// carries the one discoverable per-card destructive action (delete) — its trigger/panel stop click
// propagation so opening it never fires the card's own onClick (navigate to the collection).

import type { ReactNode } from "react";
import { useState } from "react";
import type { Collection, CollectionHealth } from "../../api/collections";
import { Chip, type ChipTone } from "../../components/Chip";
import { OverflowMenu } from "../../components/OverflowMenu";
import { OverflowMenuItem } from "../../components/OverflowMenuItem";
import { theme as t } from "../../theme";
import { lastIngestLabel, parserBadge, probeVerdict } from "./collectionHealth";
import { CollectionTagChips } from "./CollectionTagChips";
import { DeleteCollectionDialog } from "./DeleteCollectionDialog";
import { humanizeProviderLabel } from "./providerKindLabels";
import { useDeleteCollection } from "./state/useDeleteCollection";

interface CollectionCardProps {
  collection: Collection;
  health: CollectionHealth | null;
  healthError: string | null;
  docCount: number | null;
  /** Whether this collection owns at least one RUNNING job right now — the ONLY condition that
   *  earns the avatar forge orange (brand.md: orange marks the one active thing, never a static
   *  at-rest identity mark shared by every card in the grid). */
  jobRunning: boolean;
  onClick: () => void;
  /** Called after this card's collection is deleted, so the parent grid can refetch and drop it. */
  onDeleted: () => void;
}

const MAX_FORMATS_SHOWN = 2;

// Maps a verdict's Chip tone to the small status dot's background — kept local since only this
// card renders a bare dot (everywhere else a verdict renders as a full Chip).
const TONE_DOT: Partial<Record<ChipTone, string>> = {
  ok: t.color.ok, warn: t.color.warn, error: t.color.error, dim: t.color.mute,
};

/** "pdf, docx" for a short list, "pdf, docx +6 formats" once it would otherwise crowd the card. */
function formatsSummary(formats: string[]): string {
  if (formats.length <= MAX_FORMATS_SHOWN) return formats.join(", ");
  return `${formats.slice(0, MAX_FORMATS_SHOWN).join(", ")} +${formats.length - MAX_FORMATS_SHOWN} formats`;
}

/** A compact label/value pair used for the doc/chunk/last-ingest metric row. */
function Metric({ label, value }: { label: string; value: ReactNode }) {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 1, minWidth: 0 }}>
      <span style={{ color: t.color.mute, fontSize: t.font.size.xs, fontWeight: 600, textTransform: "uppercase", letterSpacing: "0.04em" }}>
        {label}
      </span>
      <span style={{ fontFamily: t.font.mono, fontSize: t.font.size.m, color: t.color.text, minWidth: 0 }}>
        {value}
      </span>
    </div>
  );
}

/**
 * The "Last ingest" metric's value — an "imported <relative-time>" label (see `lastIngestLabel`'s
 * own doc for why that fallback exists) is too long to survive the metric column's width at full
 * precision. Rather than ellipsis-truncating the relative time itself (the one number that
 * actually matters here), split "imported" off into its own small tag and always render the
 * relative time whole.
 */
function LastIngestValue({ label }: { label: string }) {
  const importedMatch = label.match(/^imported\s+(.+)$/);
  if (!importedMatch) {
    return <span style={{ whiteSpace: "nowrap" }}>{label}</span>;
  }
  return (
    <span style={{ display: "flex", alignItems: "baseline", gap: 4, minWidth: 0 }}>
      <span style={{ color: t.color.mute, fontSize: t.font.size.xs, fontWeight: 600, textTransform: "uppercase", letterSpacing: "0.03em", flexShrink: 0 }}>
        imported
      </span>
      <span style={{ whiteSpace: "nowrap" }}>{importedMatch[1]}</span>
    </span>
  );
}

export function CollectionCard({ collection, health, healthError, docCount, jobRunning, onClick, onDeleted }: CollectionCardProps) {
  const [hover, setHover] = useState(false);
  const [confirmingDelete, setConfirmingDelete] = useState(false);
  const { deleting, error: deleteError, remove } = useDeleteCollection();
  const verdict = probeVerdict(health, healthError);
  const parser = parserBadge(health);
  const chunkCount = health?.search.index.vector_count;
  const lastIngest = lastIngestLabel(health, collection.created_at);

  const handleConfirmDelete = async () => {
    const ok = await remove({ id: collection.id, name: collection.name });
    if (ok) {
      setConfirmingDelete(false);
      onDeleted();
    }
  };

  return (
    <div
      onClick={onClick}
      onMouseEnter={() => setHover(true)}
      onMouseLeave={() => setHover(false)}
      style={{
        position: "relative", overflow: "hidden", cursor: "pointer",
        background: t.color.surface,
        border: `1px solid ${hover ? t.color.accentLine : t.color.line}`,
        borderRadius: t.radius.l, padding: t.space.l,
        display: "flex", flexDirection: "column", gap: t.space.m,
        boxShadow: hover ? t.shadow.md : t.shadow.sm,
        transform: hover ? "translateY(-2px)" : "none",
        transition: "transform .18s ease, box-shadow .18s ease, border-color .18s ease",
      }}
    >
      {/* accent hairline that lights up on hover */}
      <div style={{ position: "absolute", inset: 0, borderTop: `2px solid ${t.color.accent}`, opacity: hover ? 1 : 0, transition: "opacity .18s ease", pointerEvents: "none" }} />

      <div style={{ display: "flex", alignItems: "flex-start", gap: t.space.m }}>
        <span
          title={jobRunning ? "A job is running for this collection" : undefined}
          style={{
            width: 38, height: 38, flexShrink: 0, borderRadius: t.radius.m, display: "grid", placeItems: "center",
            // Steel at rest — orange is earned ONLY by an actual running job, never a static
            // per-card identity mark (brand.md: orange is the one active thing, not decoration).
            background: jobRunning ? t.color.accentSoft : t.color.surface2,
            color: jobRunning ? t.color.accent : t.color.dim,
            fontFamily: t.font.display, fontWeight: 700, fontSize: t.font.size.xl,
          }}
        >
          {collection.name.slice(0, 1).toUpperCase()}
        </span>
        <div style={{ minWidth: 0, flex: 1 }}>
          <div style={{ display: "flex", alignItems: "center", gap: t.space.s, flexWrap: "wrap" }}>
            <strong style={{ fontSize: t.font.size.xl, fontWeight: 600, color: t.color.text, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
              {collection.name}
            </strong>
            {collection.needs_reindex && <Chip tone="warn" title="A config change requires reindexing">needs reindex</Chip>}
          </div>
          <div style={{ display: "flex", alignItems: "center", gap: 6, marginTop: 4 }}>
            <span style={{ width: 7, height: 7, borderRadius: t.radius.pill, background: TONE_DOT[verdict.tone] ?? t.color.mute, flexShrink: 0 }} />
            <span style={{ color: t.color.dim, fontSize: t.font.size.s }} title={verdict.detail}>{verdict.label}</span>
          </div>
        </div>
        <OverflowMenu label={`Actions for ${collection.name}`}>
          <OverflowMenuItem tone="danger" onClick={() => setConfirmingDelete(true)}>Delete collection</OverflowMenuItem>
        </OverflowMenu>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: t.space.m }}>
        <Metric label="Documents" value={docCount !== null ? docCount.toLocaleString() : "…"} />
        <Metric label="Chunks" value={chunkCount !== undefined ? chunkCount.toLocaleString() : "…"} />
        <Metric label="Last ingest" value={<LastIngestValue label={lastIngest} />} />
      </div>

      <div style={{ display: "flex", alignItems: "center", gap: t.space.s, flexWrap: "wrap" }}>
        {/* Steel, not orange — a parser badge is metadata, not "the one thing being worked" (brand.md
            reserves forge orange for the single active/primary thing on screen). Humanized via the
            shared provider-kind vocabulary so raw graph tokens (e.g. "granite_docling") never leak
            onto the card. */}
        {parser && <Chip tone="info">{humanizeProviderLabel("parser", parser)}</Chip>}
        <Chip tone="neutral">{formatsSummary(collection.supported_formats)}</Chip>
      </div>

      <CollectionTagChips tags={collection.tags} />

      {confirmingDelete && (
        <DeleteCollectionDialog
          collectionName={collection.name}
          pending={deleting}
          error={deleteError}
          onConfirm={handleConfirmDelete}
          onCancel={() => setConfirmingDelete(false)}
        />
      )}
    </div>
  );
}
