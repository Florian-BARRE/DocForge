// ====== Code Summary ======
// The small circular step-number pill shared by every numbered card in the search rail — the plain
// read-only node steps AND the toggleable Reranking step now both carry one, so the rail's numbering
// is either "every top-level step" or "none", never a mix (Query understanding, the one exception,
// is nested inside step 1 instead of being a sibling — see SearchPipelineRail).

import { theme } from "../../theme";

export function StepNumberBadge({ step }: { step: number }) {
  return (
    <span
      style={{
        width: 24, height: 24, borderRadius: "50%",
        background: theme.color.accentSoft, color: theme.color.accentSafe,
        fontSize: theme.font.size.s, fontWeight: 700,
        display: "flex", alignItems: "center", justifyContent: "center",
      }}
    >
      {step}
    </span>
  );
}
