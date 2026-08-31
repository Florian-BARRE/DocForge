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
      meta: { filterKind: "text" },
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
      meta: { filterKind: "enumMulti", enumOptions: ["pending", "processing", "done", "failed"] },
      cell: ({ row }) => <CorpusStatusChip status={row.original.status} />,
    },
    {
      id: "format",
      accessorKey: "format",
      header: "Format",
      meta: { filterKind: "enumMulti", enumOptions: supportedFormats },
      cell: ({ row }) => <Chip tone="neutral">{row.original.format}</Chip>,
    },
    {
      id: "page_count",
      accessorKey: "page_count",
      header: "Pages",
      meta: { filterKind: "numberRange", mono: true, align: "right" },
      cell: ({ row }) => row.original.page_count ?? "—",
    },
    {
      id: "file_size",
      accessorKey: "file_size",
      header: "Size",
      meta: { filterKind: "numberRange", mono: true, align: "right" },
      cell: ({ row }) => formatBytes(row.original.file_size),
    },
    {
      id: "created_at",
      accessorKey: "created_at",
      header: "Created",
      meta: { filterKind: "dateRange", mono: true },
      cell: ({ row }) => formatDateTime(row.original.created_at),
    },
    {
      id: "title",
      accessorKey: "title",
      header: "Title",
      meta: { filterKind: "text" },
      cell: ({ row }) => <span style={truncateStyle}>{row.original.title || "—"}</span>,
    },
    {
      id: "language",
      accessorKey: "language",
      header: "Language",
      meta: { filterKind: "listIn" },
      cell: ({ row }) => row.original.language ?? "—",
    },
    {
      id: "enabled",
      accessorKey: "enabled",
      header: "Enabled",
      meta: { filterKind: "bool" },
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
