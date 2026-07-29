// ====== Code Summary ======
// The chunk metadata's showcase piece — a generated field's array of atomic propositions,
// rendered as a distinct highlighted list so the metagen output reads as the chunk's key
// takeaway rather than a buried table row.

import { theme } from "../../../theme";

interface GeneratedFactsListProps {
  fieldName: string;
  facts: string[];
}

export function GeneratedFactsList({ fieldName, facts }: GeneratedFactsListProps) {
  return (
    <div
      style={{
        background: theme.color.loopSoft, border: `1px solid ${theme.color.loop}`,
        borderRadius: theme.radius.m, padding: theme.space.m,
      }}
    >
      <div
        style={{
          color: theme.color.loop, fontSize: theme.font.size.xs, fontWeight: 700,
          marginBottom: theme.space.s, textTransform: "uppercase", letterSpacing: "0.05em",
        }}
      >
        {fieldName}
      </div>
      <ul style={{ margin: 0, paddingLeft: theme.space.m, display: "flex", flexDirection: "column", gap: 6 }}>
        {facts.map((fact, i) => (
          <li key={i} style={{ fontSize: theme.font.size.s, color: theme.color.text }}>{fact}</li>
        ))}
      </ul>
    </div>
  );
}
