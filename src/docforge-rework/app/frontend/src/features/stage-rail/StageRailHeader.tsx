// ====== Code Summary ======
// The rail's header bar: identity, live validity badge, and the optional Save action (only
// rendered when the host page wants persistence right here).

import { Button } from "../../components/Button";
import { Chip } from "../../components/Chip";
import { theme } from "../../theme";

interface StageRailHeaderProps {
  title: string;
  subtitle?: string;
  valid: boolean;
  busy: boolean;
  /** A debounced config edit is armed but hasn't reached `/apply` yet — `blob` is stale. */
  debouncePending: boolean;
  issueCount: number;
  onSave?: () => void;
  saving: boolean;
  saveError: string | null;
}

export function StageRailHeader({
  title, subtitle, valid, busy, debouncePending, issueCount, onSave, saving, saveError,
}: StageRailHeaderProps) {
  const savePending = saving || busy || debouncePending;
  return (
    <header
      style={{
        display: "flex", alignItems: "center", gap: theme.space.m,
        padding: `${theme.space.s}px ${theme.space.l}px`,
        borderBottom: `1px solid ${theme.color.line}`,
      }}
    >
      <strong style={{ fontSize: theme.font.size.xl }}>{title}</strong>
      {subtitle && <span style={{ color: theme.color.dim, fontSize: theme.font.size.s }}>{subtitle}</span>}
      <Chip tone={busy ? "dim" : valid ? "ok" : "warn"}>
        {busy ? "applying…" : valid ? "valid" : `${issueCount} issue${issueCount === 1 ? "" : "s"}`}
      </Chip>
      {saveError && <span style={{ color: theme.color.error, fontSize: theme.font.size.s }}>{saveError}</span>}
      {onSave && (
        <Button
          variant="primary"
          onClick={onSave}
          disabled={savePending || !valid}
          title={
            !valid ? "Fix every issue before saving"
              : debouncePending ? "Waiting for pending edits to apply"
                : undefined
          }
          style={{ marginLeft: "auto" }}
        >
          {saving ? "saving…" : "Save pipeline"}
        </Button>
      )}
    </header>
  );
}
