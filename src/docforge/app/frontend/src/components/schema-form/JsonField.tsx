// JSON editor for array/object config fields (e.g. metagen targets) — the generic form's
// structured branch. The draft is parsed on every keystroke but COMMITTED only when valid,
// so the config never receives a raw string; while focused, external resyncs are suppressed
// (otherwise every committed edit would reformat the text under the cursor).
import { useEffect, useState } from "react";

import { theme } from "../../theme";

export interface JsonFieldProps {
  /** The current (parsed) value from the config. */
  value: unknown;
  /** Called with the PARSED value — only when the draft is valid JSON. */
  onChange: (value: unknown) => void;
}

export function JsonField({ value, onChange }: JsonFieldProps) {
  const [draft, setDraft] = useState(() => JSON.stringify(value ?? null, null, 2));
  const [error, setError] = useState<string | null>(null);
  const [focused, setFocused] = useState(false);

  // Resync from the outside (node switch, undo) only when the user is not typing.
  useEffect(() => {
    if (!focused) {
      setDraft(JSON.stringify(value ?? null, null, 2));
      setError(null);
    }
  }, [value, focused]);

  const handleChange = (text: string) => {
    setDraft(text);
    try {
      onChange(JSON.parse(text));
      setError(null);
    } catch {
      setError("invalid JSON — changes not applied yet");
    }
  };

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 2 }}>
      <textarea
        rows={Math.min(14, Math.max(3, draft.split("\n").length))}
        spellCheck={false}
        style={{
          background: theme.color.surface2,
          color: theme.color.text,
          border: `1px solid ${error ? theme.color.error : theme.color.line}`,
          borderRadius: theme.radius.m,
          padding: "6px 8px",
          fontSize: theme.font.size.s,
          fontFamily: theme.font.mono,
          width: "100%",
          resize: "vertical",
        }}
        value={draft}
        onChange={(e) => handleChange(e.target.value)}
        onFocus={() => setFocused(true)}
        onBlur={() => setFocused(false)}
      />
      {error && (
        <span style={{ color: theme.color.error, fontSize: theme.font.size.xs }}>{error}</span>
      )}
    </div>
  );
}
