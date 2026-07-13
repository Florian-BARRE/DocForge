// ====== Code Summary ======
// The query row: free-text input (Enter submits), a result-limit number input, and the submit
// button — the primary controls of the Search Lab.

import { inputStyle } from "../../components/inputStyle";
import { Button } from "../../components/Button";
import { theme } from "../../theme";

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
      <div style={{ width: 80 }}>
        <input
          type="number"
          min={1}
          value={limit}
          onChange={(e) => onLimitChange(Number(e.target.value))}
          style={inputStyle}
          title="Result limit"
        />
      </div>
      <Button variant="primary" disabled={loading || !query.trim()} onClick={onSubmit}>
        {loading ? "searching…" : "Search"}
      </Button>
    </div>
  );
}
