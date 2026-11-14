// ====== Code Summary ======
// One-time reveal of a freshly created key's plaintext. The plaintext lives only in the parent's
// transient state (never persisted, never refetched) — this modal is the only place it is ever
// rendered, and closing it is the caller's cue to drop that state for good.

import { useId, useState } from "react";
import type { CreatedApiKey } from "../../api/auth";
import { Button } from "../../components/Button";
import { Dialog } from "../../components/dialog/Dialog";
import { DialogTitle } from "../../components/dialog/DialogTitle";
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
  /** True when this reveal follows a rotation (a new secret replacing a revoked one), not a brand
   *  new key — the heading is the only thing that differs. */
  rotated?: boolean;
}

export function CreatedKeyModal({ createdKey, onClose, rotated }: CreatedKeyModalProps) {
  const [copied, setCopied] = useState(false);
  const titleId = useId();

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(createdKey.key);
      setCopied(true);
    } catch {
      // Clipboard access can be denied by the browser — the key is still visible to copy by hand.
    }
  };

  return (
    <Dialog
      onClose={onClose}
      labelledBy={titleId}
      tone="accent"
      closeOnBackdrop={false}
      portal={false}
      panelStyle={{ width: undefined }}
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
        <DialogTitle id={titleId}>
          {rotated ? "Key rotated" : "Key created"} — "{createdKey.name}"
        </DialogTitle>
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
    </Dialog>
  );
}
