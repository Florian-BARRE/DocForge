// ====== Code Summary ======
// A muted error message with an optional retry action — the shared failure placeholder for any
// top-level fetch across the app.

import { theme } from "../theme";

interface ErrorStateProps {
  message: string;
  onRetry?: () => void;
}

export function ErrorState({ message, onRetry }: ErrorStateProps) {
  return (
    <div style={{ padding: theme.space.l, color: theme.color.error, fontSize: theme.font.size.s }}>
      {message}
      {onRetry && (
        <button
          onClick={onRetry}
          style={{
            marginLeft: theme.space.s, background: "none", border: `1px solid ${theme.color.error}`,
            color: theme.color.error, borderRadius: theme.radius.s, padding: "2px 8px", cursor: "pointer",
          }}
        >
          retry
        </button>
      )}
    </div>
  );
}
