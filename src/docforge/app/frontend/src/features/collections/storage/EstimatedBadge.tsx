// ====== Code Summary ======
// A quiet "≈ estimated" tag for storage numbers that are sampled/approximated rather than an exact
// byte count — the backend flags this per store via `estimated: boolean`; this component never
// decides which stores are estimated, it only renders the flag it's given.

import { Chip } from "../../../components/Chip";

export function EstimatedBadge() {
  return (
    <Chip tone="dim" title="Approximated from row-size heuristics, not an exact byte count.">
      ≈ estimated
    </Chip>
  );
}
