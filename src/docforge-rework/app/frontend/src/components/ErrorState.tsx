// ====== Code Summary ======
// A centered failure card with an optional retry action — the shared placeholder for any
// top-level fetch failure across the app.

import { theme } from "../theme";
import { Button } from "./Button";

interface ErrorStateProps {
  message: string;
  onRetry?: () => void;
}

export function ErrorState({ message, onRetry }: ErrorStateProps) {
  return (
    <div
      style={{
        display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center",
        gap: theme.space.s, textAlign: "center", padding: theme.space.xxl, margin: "0 auto", maxWidth: 440,
      }}
    >
      <span
        style={{
          width: 36, height: 36, borderRadius: theme.radius.pill, display: "grid", placeItems: "center",
          background: theme.color.errorSoft, color: theme.color.error,
          fontFamily: theme.font.display, fontWeight: 700, fontSize: theme.font.size.l,
        }}
      >
        !
      </span>
      <div style={{ color: theme.color.text, fontSize: theme.font.size.m }}>{message}</div>
      {onRetry && (
        <Button variant="secondary" size="sm" onClick={onRetry}>
          Retry
        </Button>
      )}
    </div>
  );
}
