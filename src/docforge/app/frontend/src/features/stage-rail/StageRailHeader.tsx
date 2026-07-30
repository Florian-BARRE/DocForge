// ====== Code Summary ======
// The ingestion rail's slim action toolbar: live validity + the optional Save action. Deliberately
// NOT a titled banner — the collection name and the "Ingestion pipeline" label already live in the
// shell's page header and sub-tab, so repeating them here made a redundant third bar. Sticks to the
// top of the rail's scroll area, aligned to the content column.

import { Button } from "../../components/Button";
import { Chip } from "../../components/Chip";
import { theme } from "../../theme";

interface StageRailHeaderProps {
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
  valid, busy, debouncePending, issueCount, onSave, saving, saveError,
}: StageRailHeaderProps) {
  const savePending = saving || busy || debouncePending;
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
    </div>
  );
}
