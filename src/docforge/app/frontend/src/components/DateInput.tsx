// ====== Code Summary ======
// A token-styled `<input type="date">` wrapper — the native date/calendar-picker chrome cannot be
// restyled with CSS, so this primitive only tokenizes the field's own border/background/focus ring
// and forces `color-scheme` to follow the active app theme (so the browser's native calendar popup
// itself renders dark on ink instead of a foreign white box). Value/onChange stay plain ISO
// ("yyyy-mm-dd") strings, identical to the native element it wraps.

import { useTheme } from "../shell/useTheme";
import { theme } from "../theme";
import { inputStyle } from "./inputStyle";

interface DateInputProps {
  /** ISO date string ("yyyy-mm-dd"), or "" for no bound. */
  value: string;
  /** Receives the next ISO date string (or "" if cleared). */
  onChange: (next: string) => void;
  /** Accessible name — required since this primitive has no visible `<label>` of its own. */
  ariaLabel: string;
  style?: React.CSSProperties;
  className?: string;
}

/** A theme-correct date picker: tokenized field chrome + a native calendar popup that follows light/dark. */
export function DateInput({ value, onChange, ariaLabel, style, className }: DateInputProps) {
  // 1. `color-scheme` is the one lever the browser exposes over its own native calendar-popup
  // rendering (icon glyph, spinner, popup background) — CSS variables never reach into it.
  const { theme: activeTheme } = useTheme();

  return (
    <input
      type="date"
      className={className}
      value={value}
      aria-label={ariaLabel}
      onChange={(e) => onChange(e.target.value)}
      style={{
        ...inputStyle,
        borderRadius: theme.radius.s,
        padding: "5px 6px",
        fontSize: theme.font.size.xs,
        fontFamily: theme.font.mono,
        colorScheme: activeTheme,
        ...style,
      }}
    />
  );
}
