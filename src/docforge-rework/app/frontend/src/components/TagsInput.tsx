// ====== Code Summary ======
// A generic string-list editor — type a value, press Enter/comma to add it as a removable chip.
// Used for a collection's supported formats, a field's enum values, and keyword_list metadata.

import { useState } from "react";
import { theme } from "../theme";
import { Chip } from "./Chip";

interface TagsInputProps {
  values: string[];
  onChange: (values: string[]) => void;
  placeholder?: string;
}

export function TagsInput({ values, onChange, placeholder }: TagsInputProps) {
  const [draft, setDraft] = useState("");

  const commit = () => {
    const value = draft.trim();
    if (value && !values.includes(value)) onChange([...values, value]);
    setDraft("");
  };

  return (
    <div
      style={{
        display: "flex", flexWrap: "wrap", gap: 6, alignItems: "center",
        background: theme.color.surface2, border: `1px solid ${theme.color.line}`,
        borderRadius: theme.radius.m, padding: "6px 8px", minHeight: 34,
      }}
    >
      {values.map((value) => (
        <span key={value} style={{ display: "inline-flex", alignItems: "center", gap: 3 }}>
          <Chip tone="accent">{value}</Chip>
          <span
            onClick={() => onChange(values.filter((v) => v !== value))}
            style={{ cursor: "pointer", color: theme.color.dim, fontSize: theme.font.size.xs }}
          >
            ✕
          </span>
        </span>
      ))}
      <input
        value={draft}
        onChange={(e) => setDraft(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Enter" || e.key === ",") {
            e.preventDefault();
            commit();
          } else if (e.key === "Backspace" && !draft && values.length) {
            onChange(values.slice(0, -1));
          }
        }}
        onBlur={commit}
        placeholder={placeholder}
        style={{
          background: "none", border: "none", outline: "none", color: theme.color.text,
          fontSize: theme.font.size.s, flex: 1, minWidth: 60,
        }}
      />
    </div>
  );
}
