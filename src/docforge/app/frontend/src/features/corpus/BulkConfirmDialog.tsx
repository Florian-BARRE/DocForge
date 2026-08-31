// ====== Code Summary ======
// A modal confirm for a bulk operation — always names the affected count before committing,
// since delete/re-ingest are expensive or destructive at grid scale. Same overlay shape as
// features/auth/CreatedKeyModal.tsx (feature-local duplicate, not shared — see feature-slice
// isolation convention).

import { Button, type ButtonVariant } from "../../components/Button";
import { theme } from "../../theme";

interface BulkConfirmDialogProps {
  title: string;
  description: string;
  count: number;
  confirmLabel: string;
  variant: ButtonVariant;
  pending: boolean;
  onConfirm: () => void;
  onCancel: () => void;
}

export function BulkConfirmDialog({ title, description, count, confirmLabel, variant, pending, onConfirm, onCancel }: BulkConfirmDialogProps) {
  return (
    <div
      style={{
        position: "fixed", inset: 0, background: "rgba(0,0,0,.8)", backdropFilter: "blur(2px)", zIndex: 100,
        display: "flex", alignItems: "center", justifyContent: "center", padding: theme.space.l,
      }}
    >
      <div
        style={{
          background: theme.color.panel, border: `1px solid ${theme.color.accentLine}`, borderRadius: theme.radius.l,
          boxShadow: theme.shadow.pop, padding: theme.space.l, maxWidth: 440, width: "100%",
          display: "flex", flexDirection: "column", gap: theme.space.m,
        }}
      >
        <h2 style={{ fontFamily: theme.font.display, fontSize: theme.font.size.xl, fontWeight: 700, color: theme.color.text, margin: 0 }}>
          {title}
        </h2>
        <div style={{ color: theme.color.dim, fontSize: theme.font.size.m, lineHeight: 1.5 }}>{description}</div>
        <div style={{ fontFamily: theme.font.mono, fontSize: theme.font.size.xl, color: theme.color.accent, fontWeight: 700 }}>
          {count.toLocaleString()} document{count === 1 ? "" : "s"}
        </div>
        <div style={{ display: "flex", gap: theme.space.s, justifyContent: "flex-end" }}>
          <Button size="sm" disabled={pending} onClick={onCancel}>Cancel</Button>
          <Button variant={variant} size="sm" disabled={pending} onClick={onConfirm}>{pending ? "working…" : confirmLabel}</Button>
        </div>
      </div>
    </div>
  );
}
