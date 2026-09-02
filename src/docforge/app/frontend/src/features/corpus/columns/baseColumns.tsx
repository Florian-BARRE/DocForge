// ====== Code Summary ======
// The fixed catalogue columns every corpus grid has, regardless of the collection's metadata
// schema — filename (opens the document), status, format, page count, size, created date, title,
// language, and the enabled toggle. Each carries the `meta.filterKind` its header filter row
// dispatches on.

import type { ColumnDef } from "@tanstack/react-table";
import type { DocumentGridRow } from "../../../api/corpus";
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
      meta: { filterKind: "text", group: "document" },
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
      id: "status",
      accessorKey: "status",
      header: "Status",
      size: 120,
      meta: { filterKind: "enumMulti", enumOptions: ["pending", "processing", "done", "failed", "cancelled"], group: "document" },
      cell: ({ row }) => <CorpusStatusChip status={row.original.status} />,
    },
    {
      id: "format",
      accessorKey: "format",
      header: "Format",
      size: 100,
      meta: { filterKind: "enumMulti", enumOptions: supportedFormats, group: "document" },
      cell: ({ row }) => <Chip tone="neutral">{row.original.format}</Chip>,
    },
    {
      id: "page_count",
      accessorKey: "page_count",
      header: "Pages",
      // Wide enough that its min/max header filter never squeezes below the placeholder text.
      size: 110,
      minSize: 110,
      meta: { filterKind: "numberRange", mono: true, align: "right", group: "document" },
      cell: ({ row }) => row.original.page_count ?? "—",
    },
    {
      id: "file_size",
      accessorKey: "file_size",
      header: "Size",
      // Same floor as Pages — its filter is the same two-input numberRange control.
      size: 110,
      minSize: 110,
      meta: { filterKind: "numberRange", mono: true, align: "right", group: "document" },
      cell: ({ row }) => formatBytes(row.original.file_size),
    },
    {
      id: "created_at",
      accessorKey: "created_at",
      header: "Created",
      size: 170,
      // Its dateRange filter stacks its two inputs vertically, so this only needs to fit one native
      // date value's own width, not two side by side.
      minSize: 120,
      meta: { filterKind: "dateRange", mono: true, group: "document" },
      cell: ({ row }) => formatDateTime(row.original.created_at),
    },
    {
      id: "title",
      accessorKey: "title",
      header: "Title",
      size: 200,
      meta: { filterKind: "text", group: "document" },
      cell: ({ row }) => <span style={truncateStyle}>{row.original.title || "—"}</span>,
    },
    {
      id: "language",
      accessorKey: "language",
      header: "Language",
      size: 110,
      meta: { filterKind: "listIn", group: "document" },
      cell: ({ row }) => row.original.language ?? "—",
    },
    {
      id: "enabled",
      accessorKey: "enabled",
      header: "Enabled",
      size: 90,
      meta: { filterKind: "bool", group: "document" },
      cell: ({ row }) => (
        <CorpusEnabledToggle
          documentId={row.original.id}
          enabled={row.original.enabled}
          onChanged={(enabled) => onEnabledChanged(row.original.id, enabled)}
        />
      ),
    },
  ];
}
