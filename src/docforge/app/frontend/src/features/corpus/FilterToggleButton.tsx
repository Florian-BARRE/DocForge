// ====== Code Summary ======
// The header-bar toggle that shows/hides CorpusFilterPanel — mirrors the "Columns" button
// (ColumnVisibilityMenu) so both grid-chrome affordances read as one family. Carries a small
// accent-count badge so an applied-but-collapsed filter set stays visible instead of silently
// narrowing the grid behind a closed panel.

import { Button } from "../../components/Button";
import { Chip } from "../../components/Chip";

interface FilterToggleButtonProps {
  open: boolean;
  activeCount: number;
  onToggle: () => void;
}

export function FilterToggleButton({ open, activeCount, onToggle }: FilterToggleButtonProps) {
  return (
    <Button size="sm" onClick={onToggle} aria-expanded={open} aria-label="Toggle column filters">
      Filters
      {activeCount > 0 && <Chip tone="accent">{activeCount}</Chip>}
    </Button>
  );
}
