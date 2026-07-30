// ====== Code Summary ======
// One chunk's searchability toggle — flips the effective `enabled` state via PATCH
// /chunks/{id}/enabled and reports back both the new state and whether it needs a re-index (the
// caller decides how to render the honest "won't be searchable yet" note).

import { useState } from "react";
import { setChunkEnabled } from "../../../api/explorer";
import { Switch } from "../../../components/Switch";
import { theme } from "../../../theme";

interface ChunkEnabledToggleProps {
  chunkId: string;
  enabled: boolean;
  onChanged: (enabled: boolean, reindexRequired: boolean) => void;
}

export function ChunkEnabledToggle({ chunkId, enabled, onChanged }: ChunkEnabledToggleProps) {
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const toggle = async (next: boolean) => {
    setPending(true);
    setError(null);
    try {
      const result = await setChunkEnabled(chunkId, next);
      onChanged(result.enabled, result.reindex_required);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setPending(false);
    }
  };

  return (
    <span style={{ display: "inline-flex", alignItems: "center", gap: theme.space.xs }}>
      <Switch
        checked={enabled}
        disabled={pending}
        onChange={toggle}
        title={enabled ? "Searchable — click to disable" : "Hidden from search — click to enable"}
      />
      {error && <span style={{ color: theme.color.error, fontSize: theme.font.size.xs }}>{error}</span>}
    </span>
  );
}
