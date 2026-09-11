// ====== Code Summary ======
// Typed-confirmation gate for revoking/rotating the bootstrap ROOT key (see rootKey.ts) — losing it
// with a single misclick would lock an operator out of key management entirely, so the destructive
// action stays disabled until the operator types the key's exact name. Regular (non-root) keys keep
// the plain single-click confirm already in ApiKeyRow/KeyDetailPage; this gate is root-only.

import { useState } from "react";
import { Button } from "../../components/Button";
import { inputStyle } from "../../components/inputStyle";
import { theme } from "../../theme";

interface RootKeyConfirmGateProps {
  /** The exact text the operator must type — the root key's name. */
  expectedText: string;
  /** Label for the destructive button once unlocked, e.g. "Confirm revoke". */
  actionLabel: string;
  busy?: boolean;
  onConfirm: () => void;
  onCancel: () => void;
}

export function RootKeyConfirmGate({ expectedText, actionLabel, busy = false, onConfirm, onCancel }: RootKeyConfirmGateProps) {
  const [typed, setTyped] = useState("");
  const matches = typed.trim() === expectedText;

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: theme.space.xs }}>
      <span style={{ color: theme.color.error, fontSize: theme.font.size.xs }}>
        This is the root/bootstrap key — losing it can lock you out of key management. Type “{expectedText}” to confirm.
      </span>
      <div style={{ display: "flex", alignItems: "center", gap: theme.space.xs }}>
        <input
          autoFocus
          value={typed}
          onChange={(e) => setTyped(e.target.value)}
          placeholder={expectedText}
          aria-label={`Type "${expectedText}" to confirm`}
          style={{ ...inputStyle, width: 160 }}
        />
        <Button variant="danger" disabled={!matches || busy} onClick={onConfirm}>
          {busy ? "…" : actionLabel}
        </Button>
        <Button onClick={onCancel} disabled={busy}>Cancel</Button>
      </div>
    </div>
  );
}
