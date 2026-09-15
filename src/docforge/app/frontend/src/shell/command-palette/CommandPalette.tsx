// ====== Code Summary ======
// Root-mounted trigger for the ⌘K command palette. Deliberately hook-free (a bare conditional
// return) — the actual dialog (query state, focus trap, keyboard nav) only mounts while `open`, so a
// fresh instance builds every time it opens, same idiom as DeleteCollectionDialog.

import { CommandPaletteDialog } from "./CommandPaletteDialog";
import type { Navigate, View } from "../view";

interface CommandPaletteProps {
  open: boolean;
  view: View;
  onNavigate: Navigate;
  onClose: () => void;
}

export function CommandPalette({ open, view, onNavigate, onClose }: CommandPaletteProps) {
  if (!open) return null;
  return <CommandPaletteDialog view={view} onNavigate={onNavigate} onClose={onClose} />;
}
