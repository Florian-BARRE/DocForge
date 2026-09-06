// ====== Code Summary ======
// The fleet toolbar's tag filter — a toggle-chip multiselect over the tag vocabulary actually
// present across the loaded fleet (never a hardcoded list, see `useCollectionsFleet`'s
// `availableTags`). Mirrors the wizard's `FormatsField` suggestion-chip pattern: selected uses the
// same "accent = picked" toggle-state convention as that control, not the fleet card's at-rest
// steel tags. Renders nothing when the fleet carries no tags at all.

import { Chip } from "../../components/Chip";
import { theme } from "../../theme";

interface TagFilterChipsProps {
  availableTags: string[];
  selectedTags: string[];
  onSelectedTagsChange: (tags: string[]) => void;
}

export function TagFilterChips({ availableTags, selectedTags, onSelectedTagsChange }: TagFilterChipsProps) {
  if (availableTags.length === 0) return null;

  const toggle = (tag: string) => {
    if (selectedTags.includes(tag)) onSelectedTagsChange(selectedTags.filter((t) => t !== tag));
    else onSelectedTagsChange([...selectedTags, tag]);
  };

  return (
    <div role="group" aria-label="Filter collections by tag" style={{ display: "flex", alignItems: "center", gap: 6, flexWrap: "wrap" }}>
      <span style={{ color: theme.color.dim, fontSize: theme.font.size.s }}>Tags</span>
      {availableTags.map((tag) => {
        const selected = selectedTags.includes(tag);
        return (
          <button
            key={tag}
            type="button"
            onClick={() => toggle(tag)}
            aria-pressed={selected}
            style={{ background: "none", border: "none", padding: 0, cursor: "pointer" }}
          >
            <Chip tone={selected ? "accent" : "dim"}>{tag}</Chip>
          </button>
        );
      })}
    </div>
  );
}
