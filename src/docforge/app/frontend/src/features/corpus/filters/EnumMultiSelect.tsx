// ====== Code Summary ======
// A compact multi-select for a closed set of choices (status, format, an `enum` metadata field) —
// a button showing the current picks that opens a checkbox popover, rather than a native
// <select multiple> (poor UX for 3-6 short options behind a header filter cell).

import { useEffect, useRef, useState } from "react";
import { Chip } from "../../../components/Chip";
import { theme } from "../../../theme";

interface EnumMultiSelectProps {
  options: string[];
  values: string[];
  onChange: (values: string[]) => void;
  ariaLabel?: string;
}

export function EnumMultiSelect({ options, values, onChange, ariaLabel }: EnumMultiSelectProps) {
  const [open, setOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const onClickAway = (e: MouseEvent) => {
      if (rootRef.current && !rootRef.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", onClickAway);
    return () => document.removeEventListener("mousedown", onClickAway);
  }, [open]);

  const toggle = (option: string) => {
    onChange(values.includes(option) ? values.filter((v) => v !== option) : [...values, option]);
  };

  return (
    <div ref={rootRef} style={{ position: "relative" }}>
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-label={ariaLabel}
        aria-haspopup="true"
        aria-expanded={open}
        style={{
          width: "100%", textAlign: "left", background: theme.color.surface2, border: `1px solid ${theme.color.line}`,
          borderRadius: theme.radius.s, padding: "5px 6px", fontSize: 12, color: values.length ? theme.color.text : theme.color.mute,
          cursor: "pointer",
        }}
      >
        {values.length ? `${values.length} selected` : "any"}
      </button>
      {open && (
        <div
          style={{
            position: "absolute", top: "calc(100% + 4px)", left: 0, zIndex: 20, minWidth: 160,
            background: theme.color.panel, border: `1px solid ${theme.color.line}`, borderRadius: theme.radius.m,
            boxShadow: theme.shadow.pop, padding: theme.space.xs, display: "flex", flexDirection: "column", gap: 2,
          }}
        >
          {options.map((option) => (
            <label
              key={option}
              style={{
                display: "flex", alignItems: "center", gap: 6, padding: "3px 6px", borderRadius: theme.radius.s,
                cursor: "pointer", fontSize: 12, color: theme.color.text,
              }}
            >
              <input type="checkbox" checked={values.includes(option)} onChange={() => toggle(option)} />
              {option}
            </label>
          ))}
          {values.length > 0 && (
            <div style={{ borderTop: `1px solid ${theme.color.line}`, marginTop: 2, paddingTop: 4, display: "flex", flexWrap: "wrap", gap: 4 }}>
              {values.map((v) => <Chip key={v} tone="accent">{v}</Chip>)}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
