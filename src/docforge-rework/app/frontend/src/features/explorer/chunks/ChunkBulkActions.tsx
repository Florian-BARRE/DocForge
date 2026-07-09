// ====== Code Summary ======
// The multi-select bulk enable/disable bar above the chunk list — applies one state to every
// selected chunk via PATCH /chunks/enabled and surfaces the reindex/not-found fallout.

import { useState } from "react";
import type { BulkChunkEnabledResponse } from "../../../api/explorer";
import { Button } from "../../../components/Button";
import { theme } from "../../../theme";

interface ChunkBulkActionsProps {
  selectedCount: number;
  onApply: (enabled: boolean) => Promise<BulkChunkEnabledResponse>;
}

export function ChunkBulkActions({ selectedCount, onApply }: ChunkBulkActionsProps) {
  const [pending, setPending] = useState(false);
  const [note, setNote] = useState<string | null>(null);

  if (selectedCount === 0) return null;

  const apply = async (enabled: boolean) => {
    setPending(true);
    setNote(null);
    try {
      const response = await onApply(enabled);
      const reindexCount = response.results.filter((result) => result.reindex_required).length;
      const parts: string[] = [];
      if (reindexCount > 0) parts.push(`${reindexCount} won't be searchable until re-indexed`);
      if (response.not_found.length > 0) parts.push(`${response.not_found.length} not found`);
      setNote(parts.join(" · ") || null);
    } finally {
      setPending(false);
    }
  };

  return (
    <div
      style={{
        display: "flex", alignItems: "center", gap: theme.space.s,
        background: theme.color.panel, border: `1px solid ${theme.color.line}`,
        borderRadius: theme.radius.s, padding: theme.space.s,
      }}
    >
      <span style={{ fontSize: theme.font.size.s, color: theme.color.dim }}>{selectedCount} selected</span>
      <Button disabled={pending} onClick={() => apply(true)}>Enable</Button>
      <Button disabled={pending} onClick={() => apply(false)}>Disable</Button>
      {note && <span style={{ fontSize: theme.font.size.xs, color: theme.color.warn }}>{note}</span>}
    </div>
  );
}
