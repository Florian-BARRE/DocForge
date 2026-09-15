// ====== Code Summary ======
// The grid's top header band — one `<th colSpan>` per contiguous run of columns sharing the same
// `meta.group`, labelled with the family name + a one-line provenance caption (GROUP_HEADER_INFO),
// so a reader sees WHERE a column comes from before reading its individual label below. Renders
// inside CorpusTable's `<thead>`, above the existing sort/label row — the whole `<thead>` is
// `position: sticky`, so both rows stick together with no extra CSS here. `colSpan` sums always
// match the fixed `<colgroup>` widths exactly (same columns, same order, no independent sizing).
// A reorder drag can fragment a family into several runs — expected and harmless, it just reads as
// several same-toned bands instead of one.

import type { Column } from "@tanstack/react-table";
import type { DocumentGridRow } from "../../api/corpus";
import { theme } from "../../theme";
import { GROUP_HEADER_INFO } from "./columns/columnGroups";
import { isPinnedColumn, PINNED_LAST_COLUMN_ID, type ColumnGroup } from "./types";

interface GroupRun {
  group: ColumnGroup | null;
  span: number;
  firstColumnId: string;
  sticky: boolean;
}

// The pinned select/actions columns are structural chrome (no `meta.group`) — each renders as its
// own empty spanning cell, never coalesced with a neighbouring data run.
function buildGroupRuns(columns: Column<DocumentGridRow, unknown>[]): GroupRun[] {
  const runs: GroupRun[] = [];
  for (const column of columns) {
    const pinned = isPinnedColumn(column.id);
    const group = pinned ? null : (column.columnDef.meta?.group ?? "document");
    const last = runs[runs.length - 1];
    if (!pinned && last && last.group === group) {
      last.span += 1;
    } else {
      runs.push({ group, span: 1, firstColumnId: column.id, sticky: column.id === PINNED_LAST_COLUMN_ID });
    }
  }
  return runs;
}

interface GroupHeaderRowProps {
  columns: Column<DocumentGridRow, unknown>[];
}

export function GroupHeaderRow({ columns }: GroupHeaderRowProps) {
  const runs = buildGroupRuns(columns);

  return (
    <tr>
      {runs.map((run, index) => {
        if (run.group === null) {
          return (
            <th
              key={run.firstColumnId}
              aria-hidden
              style={{
                padding: 0, borderBottom: `1px solid ${theme.color.lineStrong}`,
                ...(run.sticky
                  ? { position: "sticky", right: 0, background: theme.color.surface, borderLeft: `1px solid ${theme.color.line}`, zIndex: 1 }
                  : {}),
              }}
            />
          );
        }
        const info = GROUP_HEADER_INFO[run.group];
        return (
          <th
            key={run.firstColumnId}
            colSpan={run.span}
            style={{
              textAlign: "left", padding: `4px ${theme.space.m}px`,
              background: info.tint,
              borderTop: `2px solid ${info.accent}`,
              borderBottom: `1px solid ${theme.color.lineStrong}`,
              borderLeft: index > 0 ? `1px solid ${theme.color.line}` : "none",
            }}
          >
            <span style={{
              fontSize: theme.font.size.xs, fontWeight: theme.font.weight.semibold,
              textTransform: "uppercase", letterSpacing: "0.04em", color: theme.color.text,
            }}
            >
              {info.label}
            </span>
            <span style={{ marginLeft: 6, fontSize: theme.font.size.xs, color: theme.color.dim }}>
              {info.caption}
            </span>
          </th>
        );
      })}
    </tr>
  );
}
