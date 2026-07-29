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
    <div style={{ display: "flex", gap: theme.space.s, alignItems: "flex-end" }}>
      <div style={{ flex: 1 }}>
        <input
          value={query}
          onChange={(e) => onQueryChange(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && onSubmit()}
          placeholder="Search this collection…"
          style={inputStyle}
        />
      </div>
      <div style={{ width: 80 }} title="Result limit">
        <NumberField
          value={limit}
          min={MIN_LIMIT}
          style={inputStyle}
          onChange={(value) => onLimitChange(value === undefined ? MIN_LIMIT : Math.max(MIN_LIMIT, value))}
        />
      </div>
      <Button variant="primary" disabled={loading || !query.trim() || limit < MIN_LIMIT} onClick={onSubmit}>
        {loading ? "searching…" : "Search"}
      </Button>
    </div>
  );
}
