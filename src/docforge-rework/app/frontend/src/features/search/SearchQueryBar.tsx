// ====== Code Summary ======
// The query row: free-text input (Enter submits), a result-limit number input, and the submit
// button — the primary controls of the Search Lab.

import { inputStyle } from "../../components/inputStyle";
import { Button } from "../../components/Button";
import { NumberField } from "../../components/schema-form/NumberField";
import { theme } from "../../theme";

const MIN_LIMIT = 1;

interface SearchQueryBarProps {
  query: string;
  onQueryChange: (value: string) => void;
  limit: number;
  onLimitChange: (value: number) => void;
  loading: boolean;
  onSubmit: () => void;
}

export function SearchQueryBar({ query, onQueryChange, limit, onLimitChange, loading, onSubmit }: SearchQueryBarProps) {
  return (
    <div
      style={{
        display: "flex", gap: theme.space.s, alignItems: "center", padding: theme.space.s,
        background: theme.color.surface, border: `1px solid ${theme.color.line}`, borderRadius: theme.radius.l,
        boxShadow: theme.shadow.sm,
      }}
    >
      <div style={{ flex: 1 }}>
        <input
          value={query}
          onChange={(e) => onQueryChange(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && onSubmit()}
          placeholder="Search this collection…"
          style={{ ...inputStyle, border: "none", background: "transparent", fontSize: theme.font.size.l, padding: "6px 4px" }}
        />
      </div>
      <div style={{ width: 72 }} title="Result limit">
        <NumberField
          value={limit}
          min={MIN_LIMIT}
          style={{ ...inputStyle, borderRadius: theme.radius.m, textAlign: "center" }}
          onChange={(value) => onLimitChange(value === undefined ? MIN_LIMIT : Math.max(MIN_LIMIT, value))}
        />
      </div>
      <Button variant="primary" disabled={loading || !query.trim() || limit < MIN_LIMIT} onClick={onSubmit}>
        {loading ? "searching…" : "Search"}
      </Button>
    </div>
  );
}
