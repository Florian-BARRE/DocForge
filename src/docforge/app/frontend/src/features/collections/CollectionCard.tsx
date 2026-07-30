// ====== Code Summary ======
// One collection summary card in the list grid — an ember monogram, the name, supported formats,
// field count, reindex flag. Lifts + reveals its accent edge on hover.

import { useState } from "react";
import type { Collection } from "../../api/collections";
import { Chip } from "../../components/Chip";
import { theme as t } from "../../theme";

interface CollectionCardProps {
  collection: Collection;
  onClick: () => void;
}

export function CollectionCard({ collection, onClick }: CollectionCardProps) {
  const [hover, setHover] = useState(false);
  return (
    <div
      onClick={onClick}
      onMouseEnter={() => setHover(true)}
      onMouseLeave={() => setHover(false)}
      style={{
        position: "relative", overflow: "hidden",
        background: t.color.surface,
        border: `1px solid ${hover ? t.color.accentLine : t.color.line}`,
        borderRadius: t.radius.l, padding: t.space.l, cursor: "pointer",
        display: "flex", flexDirection: "column", gap: t.space.m,
        boxShadow: hover ? t.shadow.md : t.shadow.sm,
        transform: hover ? "translateY(-2px)" : "none",
        transition: "transform .18s ease, box-shadow .18s ease, border-color .18s ease",
      }}
    >
      {/* accent hairline that lights up on hover */}
      <div style={{ position: "absolute", inset: 0, borderTop: `2px solid ${t.color.accent}`, opacity: hover ? 1 : 0, transition: "opacity .18s ease", pointerEvents: "none" }} />
      <div style={{ display: "flex", alignItems: "center", gap: t.space.m }}>
        <span
          style={{
            width: 38, height: 38, flexShrink: 0, borderRadius: t.radius.m, display: "grid", placeItems: "center",
            background: t.color.accentSoft, color: t.color.accent,
            fontFamily: t.font.display, fontWeight: 700, fontSize: t.font.size.xl,
          }}
        >
          {collection.name.slice(0, 1).toUpperCase()}
        </span>
        <div style={{ minWidth: 0, flex: 1 }}>
          <div style={{ display: "flex", alignItems: "center", gap: t.space.s }}>
            <strong style={{ fontSize: t.font.size.xl, fontWeight: 600, color: t.color.text, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
              {collection.name}
            </strong>
            {collection.needs_reindex && <Chip tone="warn" title="A config change requires reindexing">needs reindex</Chip>}
          </div>
          <div style={{ color: t.color.dim, fontSize: t.font.size.m, marginTop: 2 }}>
            {collection.fields.length} field{collection.fields.length === 1 ? "" : "s"}
          </div>
        </div>
      </div>
      <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
        {collection.supported_formats.map((f) => <Chip key={f} tone="neutral">{f}</Chip>)}
      </div>
    </div>
  );
}
