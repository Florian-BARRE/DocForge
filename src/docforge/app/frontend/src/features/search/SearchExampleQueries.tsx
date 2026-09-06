// ====== Code Summary ======
// Pre-query teaching panel for the Search Lab's resting state — a few example queries a user can
// click to fill the query bar instantly, so a brand-new collection's empty result column reads as
// a hint rather than a dead end. Clicking only fills the text; it never auto-submits, so the
// existing "type then press Search/Enter" flow stays exactly as before.

import { Chip } from "../../components/Chip";
import { theme } from "../../theme";

const EXAMPLE_QUERIES = [
  "What are the key obligations described in this document?",
  "Summarize the main findings.",
  "List all defined terms and their definitions.",
  "Find sections that mention compliance requirements.",
  "What is the effective date and who are the parties involved?",
];

interface SearchExampleQueriesProps {
  onSelect: (query: string) => void;
}

export function SearchExampleQueries({ onSelect }: SearchExampleQueriesProps) {
  return (
    <div
      style={{
        background: theme.color.surface, border: `1px dashed ${theme.color.lineStrong}`,
        borderRadius: theme.radius.l, padding: theme.space.l,
        display: "flex", flexDirection: "column", gap: theme.space.m,
      }}
    >
      <div style={{ color: theme.color.dim, fontSize: theme.font.size.s }}>
        Run a query to see ranked hits — or try one of these:
      </div>
      <div style={{ display: "flex", flexWrap: "wrap", gap: theme.space.s }}>
        {EXAMPLE_QUERIES.map((example) => (
          <button
            key={example}
            type="button"
            onClick={() => onSelect(example)}
            style={{ background: "none", border: "none", padding: 0, cursor: "pointer", textAlign: "left" }}
          >
            <Chip tone="neutral">{example}</Chip>
          </button>
        ))}
      </div>
    </div>
  );
}
