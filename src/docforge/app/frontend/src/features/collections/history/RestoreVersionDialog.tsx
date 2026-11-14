// ====== Code Summary ======
// Modal confirm for restoring a config version — shows the diff from the CURRENT head to the target
// version (what the restore will change) and requires an explicit confirm. Restoring always writes a
// NEW version. The overlay shell is the shared `ConfirmDialog`.

import type { ConfigDiffEntry } from "../../../api/configVersions";
import { ConfirmDialog } from "../../../components/dialog/ConfirmDialog";
import { theme } from "../../../theme";
import { ConfigDiffView } from "./ConfigDiffView";

interface RestoreVersionDialogProps {
  version: number;
  head: number;
  changes: ConfigDiffEntry[] | null;
  pending: boolean;
  error: string | null;
  onConfirm: () => void;
  onCancel: () => void;
}

export function RestoreVersionDialog({ version, head, changes, pending, error, onConfirm, onCancel }: RestoreVersionDialogProps) {
  return (
    <ConfirmDialog
      title={<>Restore version <span style={{ fontFamily: theme.font.mono }}>v{version}</span></>}
      maxWidth={720}
      blur={false}
      confirmLabel={`Restore v${version}`}
      pendingLabel="restoring…"
      pending={pending}
      confirmDisabled={changes === null}
      error={error}
      onConfirm={onConfirm}
      onCancel={onCancel}
    >
      <div style={{ color: theme.color.dim, fontSize: theme.font.size.m, lineHeight: 1.5 }}>
        Changes from the current <span style={{ fontFamily: theme.font.mono }}>v{head}</span>. The restore
        writes a new version; current provider keys at the same endpoint are kept.
      </div>
      {changes === null ? (
        <div style={{ color: theme.color.dim, fontSize: theme.font.size.m }}>loading diff…</div>
      ) : (
        <ConfigDiffView changes={changes} />
      )}
    </ConfirmDialog>
  );
}
