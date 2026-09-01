// ====== Code Summary ======
// The branded crash card shown by <ErrorBoundary> when a routed view throws during render.
// Presentational only — no recovery logic of its own, just the two actions it's handed.

import { theme as t } from "../theme";
import { Button } from "../components/Button";

interface ErrorFallbackProps {
  error: Error;
  onReload: () => void;
  onBackToCollections?: () => void;
}

export function ErrorFallback({ error, onReload, onBackToCollections }: ErrorFallbackProps) {
  return (
    <div
      role="alert"
      style={{
        display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center",
        gap: t.space.m, textAlign: "center", padding: t.space.xxl, margin: "0 auto", maxWidth: 480,
        height: "100%",
      }}
    >
      <span
        aria-hidden
        style={{
          width: 44, height: 44, borderRadius: t.radius.pill, display: "grid", placeItems: "center",
          background: t.color.errorSoft, color: t.color.error,
          fontFamily: t.font.display, fontWeight: 700, fontSize: t.font.size.xl,
        }}
      >
        !
      </span>
      <h1
        style={{
          fontFamily: t.font.display, fontWeight: 700, fontSize: t.font.size.xxl,
          letterSpacing: "-0.02em", color: t.color.text,
        }}
      >
        Something broke mid-forge
      </h1>
      <p style={{ color: t.color.dim, fontSize: t.font.size.m, lineHeight: 1.5 }}>
        This view hit an unexpected error and could not render. Reloading usually clears it.
      </p>
      <div
        className="mono"
        style={{
          width: "100%", background: t.color.surface2, border: `1px solid ${t.color.line}`,
          borderRadius: t.radius.m, padding: `${t.space.s}px ${t.space.m}px`,
          color: t.color.mute, fontSize: t.font.size.s, textAlign: "left", wordBreak: "break-word",
        }}
      >
        {error.message || String(error)}
      </div>
      <div style={{ display: "flex", gap: t.space.s, marginTop: t.space.s }}>
        {onBackToCollections && (
          <Button variant="secondary" size="md" onClick={onBackToCollections}>
            Back to Collections
          </Button>
        )}
        <Button variant="primary" size="md" onClick={onReload}>
          Reload
        </Button>
      </div>
    </div>
  );
}
