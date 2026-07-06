// ====== Code Summary ======
// One collection summary card in the list grid — name, formats, field count, reindex flag.

import type { Collection } from "../../api/collections";
import { Chip } from "../../components/Chip";
import { theme } from "../../theme";

interface CollectionCardProps {
  collection: Collection;
  onClick: () => void;
}

export function CollectionCard({ collection, onClick }: CollectionCardProps) {
  return (
    <div
      onClick={onClick}
      style={{
        background: theme.color.card, border: `1px solid ${theme.color.line}`,
        borderRadius: theme.radius.m, padding: theme.space.m, cursor: "pointer",
        display: "flex", flexDirection: "column", gap: theme.space.xs,
      }}
      onMouseEnter={(e) => (e.currentTarget.style.background = theme.color.cardHover)}
      onMouseLeave={(e) => (e.currentTarget.style.background = theme.color.card)}
    >
      <div style={{ display: "flex", alignItems: "center", gap: theme.space.s }}>
        <strong style={{ fontSize: theme.font.size.l }}>{collection.name}</strong>
        {collection.needs_reindex && <Chip tone="warn" title="A config change requires reindexing">needs reindex</Chip>}
      </div>
      <div style={{ display: "flex", flexWrap: "wrap", gap: 4 }}>
        {collection.supported_formats.map((f) => <Chip key={f} tone="accent">{f}</Chip>)}
      </div>
      <div style={{ color: theme.color.dim, fontSize: theme.font.size.s }}>
        {collection.fields.length} field(s)
      </div>
    </div>
  );
}
