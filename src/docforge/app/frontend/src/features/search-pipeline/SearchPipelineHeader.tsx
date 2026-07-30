// ====== Code Summary ======
// The search editor's slim action toolbar: live validity + Reset/Save, nothing else. Deliberately
// NOT a titled banner — the collection name and the "Search pipeline" label already live in the
// shell's page header and sub-tab, so repeating them here made a redundant third bar. Sticks to the
// top of the editor's scroll area, aligned to the content column.

import { Button } from "../../components/Button";
import { Chip } from "../../components/Chip";
import { theme } from "../../theme";

interface SearchPipelineHeaderProps {
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
  valid, checking, debouncePending, issueCount, dirty, onReset, resetting, onSave, saving, saveError,
}: SearchPipelineHeaderProps) {
  const savePending = saving || resetting || checking || debouncePending;
  return (
    <div
      style={{
        position: "sticky", top: 0, zIndex: 2,
        display: "flex", alignItems: "center", gap: theme.space.s, flexWrap: "wrap",
        padding: `${theme.space.s}px 0`,
        background: "color-mix(in srgb, var(--bg) 82%, transparent)",
        backdropFilter: "blur(8px)", WebkitBackdropFilter: "blur(8px)",
        borderBottom: `1px solid ${theme.color.line}`,
      }}
    >
      <Chip tone={checking ? "dim" : valid ? "ok" : "warn"}>
        {checking ? "checking…" : valid ? "valid" : `${issueCount} issue${issueCount === 1 ? "" : "s"}`}
      </Chip>
      {saveError && <span style={{ color: theme.color.error, fontSize: theme.font.size.s }}>{saveError}</span>}
      {(onReset || onSave) && (
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
              {saving ? "saving…" : "Save"}
            </Button>
          )}
        </div>
      )}
    </div>
  );
}
