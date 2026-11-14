// ====== Code Summary ======
// Modal confirm for pointing a collection alias at THIS collection (the blue/green switch). Every
// client and every `alias:<name>` key scope follows the alias on the very next request, so the switch
// is never a single click. The overlay shell is the shared `ConfirmDialog`.

import { ConfirmDialog } from "../../../components/dialog/ConfirmDialog";
import { theme } from "../../../theme";

interface SwitchAliasDialogProps {
  alias: string;
  /** The collection the alias points at now; null when the alias does not exist yet. */
  currentTargetName: string | null;
  collectionName: string;
  pending: boolean;
  error: string | null;
  onConfirm: () => void;
  onCancel: () => void;
}

export function SwitchAliasDialog({ alias, currentTargetName, collectionName, pending, error, onConfirm, onCancel }: SwitchAliasDialogProps) {
  const mono = { fontFamily: theme.font.mono };

  return (
    <ConfirmDialog
      title={<>Switch alias <span style={mono}>{alias}</span> here</>}
      maxWidth={560}
      blur={false}
      confirmLabel="Switch alias here"
      pendingLabel="switching…"
      pending={pending}
      error={error}
      onConfirm={onConfirm}
      onCancel={onCancel}
    >
      <div style={{ color: theme.color.dim, fontSize: theme.font.size.m, lineHeight: 1.5 }}>
        {currentTargetName === null ? (
          <>The alias does not exist yet: it will be created pointing at <strong>{collectionName}</strong>.</>
        ) : (
          <>
            The alias moves from <strong>{currentTargetName}</strong> to <strong>{collectionName}</strong>. Every
            client using it — and every key scoped to <span style={mono}>alias:{alias}</span> — follows it on the
            very next request.
          </>
        )}
      </div>
    </ConfirmDialog>
  );
}
