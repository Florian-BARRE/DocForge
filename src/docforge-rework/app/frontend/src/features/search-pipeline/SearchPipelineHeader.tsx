// ====== Code Summary ======
// The search rail's header bar: identity, live validity badge (fed by a debounced /inspect, not
// a free-riding /stages/view like ingestion has), and the optional Reset/Save actions — mirrors
// StageRailHeader's shape and tone rules.

import { Button } from "../../components/Button";
import { Chip } from "../../components/Chip";
import { theme } from "../../theme";

interface SearchPipelineHeaderProps {
  title: string;
  subtitle?: string;
  valid: boolean;
  checking: boolean;
  /** A debounced config edit is armed but hasn't reached `/inspect` yet — the `valid` badge is stale. */
  debouncePending: boolean;
  issueCount: number;
  dirty: boolean;
  onReset?: () => void;
  resetting: boolean;
  onSave?: () => void;
  saving: boolean;
  saveError: string | null;
}

export function SearchPipelineHeader({
  title, subtitle, valid, checking, debouncePending, issueCount, dirty, onReset, resetting, onSave, saving, saveError,
}: SearchPipelineHeaderProps) {
  const savePending = saving || resetting || checking || debouncePending;
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
      <Chip tone={checking ? "dim" : valid ? "ok" : "warn"}>
        {checking ? "checking…" : valid ? "valid" : `${issueCount} issue${issueCount === 1 ? "" : "s"}`}
      </Chip>
      {saveError && <span style={{ color: theme.color.error, fontSize: theme.font.size.s }}>{saveError}</span>}
      <div style={{ marginLeft: "auto", display: "flex", gap: theme.space.s }}>
        {onReset && (
          <Button
            onClick={onReset}
            disabled={saving || resetting}
            title="Revert the stored search pipeline to the stock default (tracks future default changes)"
          >
            {resetting ? "resetting…" : "Reset to default"}
          </Button>
        )}
        {onSave && (
          <Button
            variant="primary"
            onClick={onSave}
            disabled={savePending || !valid || !dirty}
            title={
              !valid ? "Fix every issue before saving"
                : !dirty ? "No changes to save"
                  : debouncePending ? "Waiting for pending edits to verify"
                    : undefined
            }
          >
            {saving ? "saving…" : "Save search pipeline"}
          </Button>
        )}
      </div>
    </header>
  );
}
