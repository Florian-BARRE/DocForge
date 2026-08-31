// ====== Code Summary ======
// A single document's searchability toggle inside a grid cell — a local duplicate of
// features/explorer/DocumentEnabledToggle.tsx (feature slices never cross-import).

import { useState } from "react";
import { setDocumentEnabled } from "../../api/documents";
import { Switch } from "../../components/Switch";
import { theme } from "../../theme";

interface CorpusEnabledToggleProps {
  documentId: string;
  enabled: boolean;
  onChanged: (enabled: boolean) => void;
}

export function CorpusEnabledToggle({ documentId, enabled, onChanged }: CorpusEnabledToggleProps) {
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const toggle = async (next: boolean) => {
    setPending(true);
    setError(null);
    try {
      const response = await setDocumentEnabled(documentId, next);
      onChanged(response.enabled);
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
