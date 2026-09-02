// ====== Code Summary ======
// One-time reveal of a freshly created key's plaintext. The plaintext lives only in the parent's
// transient state (never persisted, never refetched) — this modal is the only place it is ever
// rendered, and closing it is the caller's cue to drop that state for good.

import { useId, useState } from "react";
import type { CreatedApiKey } from "../../api/auth";
import { Button } from "../../components/Button";
import { useFocusTrap } from "../../shell/useFocusTrap";
import { theme } from "../../theme";

/** A minimal key glyph, `currentColor`-only — brand.md bans emoji everywhere in the UI. */
function KeyGlyph() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"
      strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <circle cx="8" cy="15" r="4" />
      <path d="M10.5 12.5 20 3M17 6l2.5 2.5M14 9l2 2" />
    </svg>
  );
}

interface CreatedKeyModalProps {
  createdKey: CreatedApiKey;
  onClose: () => void;
}

export function CreatedKeyModal({ createdKey, onClose }: CreatedKeyModalProps) {
  const [copied, setCopied] = useState(false);
  const titleId = useId();
  const panelRef = useFocusTrap<HTMLDivElement>(onClose);

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(createdKey.key);
      setCopied(true);
    } catch {
      // Clipboard access can be denied by the browser — the key is still visible to copy by hand.
    }
  };

  return (
    <div
      style={{
        position: "fixed", inset: 0, background: "rgba(0,0,0,.8)", backdropFilter: "blur(2px)", zIndex: 100,
        display: "flex", alignItems: "center", justifyContent: "center", padding: theme.space.l,
      }}
    >
      <div
        ref={panelRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        tabIndex={-1}
        style={{
          background: theme.color.panel, border: `1px solid ${theme.color.accentLine}`,
          borderRadius: theme.radius.l, boxShadow: theme.shadow.pop, padding: theme.space.l, maxWidth: 480,
          display: "flex", flexDirection: "column", gap: theme.space.m,
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: theme.space.s }}>
          <span
            style={{
              width: 32, height: 32, borderRadius: theme.radius.pill, flexShrink: 0, display: "grid", placeItems: "center",
              background: theme.color.accentSoft, color: theme.color.accentSafe, fontSize: theme.font.size.l,
            }}
          >
            <KeyGlyph />
          </span>
          <h2 id={titleId} style={{ fontFamily: theme.font.display, fontSize: theme.font.size.xl, fontWeight: 700, color: theme.color.text, margin: 0 }}>
            Key created — "{createdKey.name}"
          </h2>
        </div>
        <div
          style={{
            background: theme.color.errorSoft, borderLeft: `3px solid ${theme.color.error}`,
            borderRadius: theme.radius.s, padding: `${theme.space.s}px ${theme.space.m}px`,
            fontSize: theme.font.size.s, color: theme.color.error,
          }}
        >
          This is the only time the full key is shown. Copy it now — it cannot be retrieved again.
        </div>
        <code
          style={{
            background: theme.color.bg, border: `1px solid ${theme.color.line}`,
            borderRadius: theme.radius.s, padding: theme.space.s,
            fontSize: theme.font.size.m, fontFamily: theme.font.mono, color: theme.color.text,
            wordBreak: "break-all",
          }}
        >
          {createdKey.key}
        </code>
        <div style={{ display: "flex", gap: theme.space.s }}>
          <Button onClick={copy}>{copied ? "copied ✓" : "Copy"}</Button>
          <Button variant="primary" onClick={onClose}>I've saved it — close</Button>
        </div>
      </div>
    </div>
  );
}
