// ====== Code Summary ======
// A collection's `tags` rendered as small muted chips — steel/dim, never forge orange (brand.md: a
// stored tag is metadata at rest, not the one active thing). Truncates to a handful with a "+N"
// overflow pill (its title lists the rest) so a heavily-tagged collection never crowds the fleet
// card. Untagged (`[]`) renders nothing.

import { Chip } from "../../components/Chip";

const MAX_TAGS_SHOWN = 3;

interface CollectionTagChipsProps {
  tags: string[];
}

export function CollectionTagChips({ tags }: CollectionTagChipsProps) {
  if (tags.length === 0) return null;

  const shown = tags.slice(0, MAX_TAGS_SHOWN);
  const overflowCount = tags.length - shown.length;

  return (
    <div style={{ display: "flex", alignItems: "center", gap: 6, flexWrap: "wrap" }}>
      {shown.map((tag) => (
        <Chip key={tag} tone="dim">{tag}</Chip>
      ))}
      {overflowCount > 0 && (
        <Chip tone="dim" title={tags.slice(MAX_TAGS_SHOWN).join(", ")}>+{overflowCount}</Chip>
      )}
    </div>
  );
}
