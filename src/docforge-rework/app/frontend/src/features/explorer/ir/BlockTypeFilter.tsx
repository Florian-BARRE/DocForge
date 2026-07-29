// ====== Code Summary ======
// The IR tab's type filter — chip list derived from the actual block types present in this
// document (never a hardcoded enum, since parsers can emit types the frontend doesn't know yet).

import { Chip } from "../../../components/Chip";

interface BlockTypeFilterProps {
  types: string[];
  active: string;
  onSelect: (type: string) => void;
}

export function BlockTypeFilter({ types, active, onSelect }: BlockTypeFilterProps) {
  return (
    <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
      {["all", ...types].map((type) => (
        <span key={type} onClick={() => onSelect(type)} style={{ cursor: "pointer" }}>
          <Chip tone={type === active ? "accent" : "neutral"}>{type}</Chip>
        </span>
      ))}
    </div>
  );
}
