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
  ariaLabel?: string;
}

/** Splits a raw string on commas and/or whitespace into trimmed, non-empty tokens — the same
 *  delimiter set a user reaches for when pasting a list ("md, html, pdf" or "md html pdf"). */
function splitIntoTokens(raw: string): string[] {
  return raw.split(/[,\s]+/).map((token) => token.trim()).filter(Boolean);
}

export function TagsInput({ values, onChange, placeholder, ariaLabel }: TagsInputProps) {
  const [draft, setDraft] = useState("");

  const commitTokens = (tokens: string[]) => {
    if (!tokens.length) return;
    const next = [...values];
    for (const token of tokens) if (!next.includes(token)) next.push(token);
    onChange(next);
  };

  // Tokenizes the WHOLE draft (not just a trimmed single value) so a value typed without ever
  // pressing Enter/comma — or one that arrived via paste, see onPaste below — still splits into
  // one chip per format/keyword instead of a single bogus "md, html, pdf" tag.
  const commit = () => {
    commitTokens(splitIntoTokens(draft));
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
          {/* Neutral, not accent — a stored tag is metadata at rest, not the one active thing. */}
          <Chip tone="neutral">{value}</Chip>
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
        onPaste={(e) => {
          // Pasting a comma/space-separated list bypasses onKeyDown entirely (no per-character
          // keydown fires for a paste) — tokenize it immediately instead of leaving one raw blob
          // in the draft until blur. Applies on-change right away, so a downstream "Next" button
          // gated on the tokenized value enables without the field ever needing to blur.
          e.preventDefault();
          const pasted = e.clipboardData.getData("text");
          commitTokens(splitIntoTokens(draft + pasted));
          setDraft("");
        }}
        onBlur={commit}
        placeholder={placeholder}
        aria-label={ariaLabel}
        style={{
          background: "none", border: "none", outline: "none", color: theme.color.text,
          fontSize: theme.font.size.s, flex: 1, minWidth: 60,
        }}
      />
    </div>
  );
}
