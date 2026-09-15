// ====== Code Summary ======
// The fixed catalogue columns every corpus grid has, regardless of the collection's metadata
// schema — filename (opens the document), title, status, format and the enabled toggle (TRUE
// document identity/state, `group: "document"`), followed by page count, language, size, created
// date and chunk count (all computed by the platform at ingestion, `group: "system"`). Emitted
// group-contiguous in that order so the grouped header row (GroupHeaderRow) reads as two clean
// bands by default. Each carries the `meta.filterKind` its header filter row dispatches on, plus
// `meta.filterable` (mirrors `filterKind !== undefined`) for the header's ColumnNatureBadges.

import type { ColumnDef } from "@tanstack/react-table";
import type { DocumentGridRow } from "../../../api/corpus";
import { DOCUMENT_STATUSES } from "../../../api/explorer";
import { Chip } from "../../../components/Chip";
import { theme } from "../../../theme";
import { CorpusEnabledToggle } from "../CorpusEnabledToggle";
import { CorpusStatusChip } from "../CorpusStatusChip";
import { formatBytes, formatDateTime } from "../format";

interface BaseColumnsArgs {
  onOpen: (documentId: string) => void;
  onEnabledChanged: (documentId: string, enabled: boolean) => void;
  supportedFormats: string[];
}

const truncateStyle: React.CSSProperties = {
  overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", display: "block", maxWidth: 260,
};

export function buildBaseColumns({ onOpen, onEnabledChanged, supportedFormats }: BaseColumnsArgs): ColumnDef<DocumentGridRow>[] {
  return [
    {
      id: "filename",
      accessorKey: "filename",
      header: "Filename",
      size: 240,
      meta: { filterKind: "text", filterable: true, group: "document" },
      cell: ({ row }) => (
        <button
          onClick={() => onOpen(row.original.id)}
          title={row.original.filename}
          style={{
            background: "none", border: "none", padding: 0, cursor: "pointer", textAlign: "left",
            color: theme.color.text, fontWeight: 500, fontSize: theme.font.size.s, ...truncateStyle,
          }}
        >
          {row.original.filename}
        </button>
      ),
    },
    {
      id: "title",
      accessorKey: "title",
      header: "Title",
      size: 200,
      meta: { filterKind: "text", filterable: true, group: "document" },
      cell: ({ row }) => <span style={truncateStyle}>{row.original.title || "—"}</span>,
    },
    {
      id: "status",
      accessorKey: "status",
      header: "Status",
      size: 120,
      meta: { filterKind: "enumMulti", filterable: true, enumOptions: DOCUMENT_STATUSES, group: "document" },
      cell: ({ row }) => (
        <CorpusStatusChip
          status={row.original.status}
          hasWarning={!!row.original.warning_reason || row.original.chunk_count === 0}
        />
      ),
    },
    {
      id: "format",
      accessorKey: "format",
      header: "Format",
      size: 100,
      meta: { filterKind: "enumMulti", filterable: true, enumOptions: supportedFormats, group: "document" },
      cell: ({ row }) => <Chip tone="neutral">{row.original.format}</Chip>,
    },
    // Deliberately kept LAST within the Document block rather than trailing the whole column set:
    // it's the one interactive control in this whole grid (a toggle, not read-only data), so it
    // must stay reachable within the always-visible leading columns — the grid's own
    // MIN_TABLE_WIDTH floor routinely overflows a typical viewport once metadata columns are
    // added, and the row-actions column pinned `position: sticky; right: 0` (CorpusTable.tsx)
    // unavoidably overlaps whatever trailing column sits at that overflow boundary at
    // scrollLeft=0 — a read-only column degrading there is a cosmetic nit; an unreachable ENABLED
    // toggle was a MAJOR usability regression (iteration-2 GUI campaign finding).
    {
      id: "enabled",
      accessorKey: "enabled",
      header: "Enabled",
      size: 90,
      meta: { filterKind: "bool", filterable: true, group: "document" },
      cell: ({ row }) => (
        <CorpusEnabledToggle
          documentId={row.original.id}
          enabled={row.original.enabled}
          onChanged={(enabled) => onEnabledChanged(row.original.id, enabled)}
        />
      ),
    },
    {
      id: "page_count",
      accessorKey: "page_count",
      header: "Pages",
      // Wide enough that its min/max header filter never squeezes below the placeholder text.
      size: 110,
      minSize: 110,
      meta: { filterKind: "numberRange", filterable: true, mono: true, align: "right", group: "system" },
      cell: ({ row }) => row.original.page_count ?? "—",
    },
    {
      id: "language",
      accessorKey: "language",
      header: "Language",
      size: 110,
      meta: { filterKind: "listIn", filterable: true, group: "system" },
      cell: ({ row }) => row.original.language ?? "—",
    },
    {
      id: "file_size",
      accessorKey: "file_size",
      header: "Size",
      // Same floor as Pages — its filter is the same two-input numberRange control.
      size: 110,
      minSize: 110,
      meta: { filterKind: "numberRange", filterable: true, mono: true, align: "right", group: "system" },
      cell: ({ row }) => formatBytes(row.original.file_size),
    },
    {
      id: "created_at",
      accessorKey: "created_at",
      header: "Created",
      // Wide enough for the mono locale timestamp (e.g. "9/10/2026, 10:30:04 PM") to clear the
      // sticky actions column without clipping.
      size: 200,
      // Its dateRange filter stacks its two inputs vertically, so this only needs to fit one native
      // date value's own width, not two side by side.
      minSize: 150,
      meta: { filterKind: "dateRange", filterable: true, mono: true, group: "system" },
      cell: ({ row }) => formatDateTime(row.original.created_at),
    },
    {
      // Display-only — not wired into the server filter/sort contract (chunk_count is absent from
      // both `DocumentFilter` and the backend's sortable-column set), so no `filterKind` and sorting
      // disabled rather than sending a field the API would reject.
      id: "chunk_count",
      accessorKey: "chunk_count",
      header: "Chunks",
      size: 90,
      minSize: 90,
      enableSorting: false,
      meta: { mono: true, align: "right", group: "system" },
      cell: ({ row }) => {
        const { chunk_count, warning_reason } = row.original;
        return (
          <span title={warning_reason ?? undefined} style={{ color: warning_reason || chunk_count === 0 ? theme.color.warnStrong : undefined }}>
            {chunk_count === null ? "—" : chunk_count}
          </span>
        );
      },
    },
  ];
}
