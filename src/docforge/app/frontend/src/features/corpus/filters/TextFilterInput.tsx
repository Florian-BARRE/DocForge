// ====== Code Summary ======
// A debounced "contains" text filter — keystrokes update the visible input instantly, but the
// parent (and therefore the /query refetch) only hears about the value 350ms after typing stops.

import { useEffect, useRef, useState } from "react";
import { inputStyle } from "../../../components/inputStyle";
import { theme } from "../../../theme";

const DEBOUNCE_MS = 350;

interface TextFilterInputProps {
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
  ariaLabel?: string;
}

export function TextFilterInput({ value, onChange, placeholder, ariaLabel }: TextFilterInputProps) {
  const [draft, setDraft] = useState(value);
  const timerRef = useRef<number>();

  // Resync from the outside (e.g. a "clear all filters" action) without fighting the user's typing.
  useEffect(() => setDraft(value), [value]);

  const handleChange = (next: string) => {
    setDraft(next);
    window.clearTimeout(timerRef.current);
    timerRef.current = window.setTimeout(() => onChange(next), DEBOUNCE_MS);
  };

  useEffect(() => () => window.clearTimeout(timerRef.current), []);

  return (
    <input
      value={draft}
      onChange={(e) => handleChange(e.target.value)}
      placeholder={placeholder ?? "contains…"}
      aria-label={ariaLabel}
      style={{ ...inputStyle, padding: `${theme.space.xs}px ${theme.space.s}px`, fontSize: theme.font.size.s }}
    />
  );
}
