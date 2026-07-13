// ====== Code Summary ======
// A muted inline warning surfaced when the backend's debug_info reports
// `late_interaction_skipped` — late interaction was requested but the collection has no colbert
// vectors, so the search fell back silently. Never a hard failure, just a notice.

import { theme } from "../../theme";

interface LateInteractionSkippedNoticeProps {
  reason: string;
}

export function LateInteractionSkippedNotice({ reason }: LateInteractionSkippedNoticeProps) {
  return (
    <div
      style={{
        color: theme.color.dim, background: theme.color.warnSoft,
        borderRadius: theme.radius.s, padding: `${theme.space.xs}px ${theme.space.s}px`,
        fontSize: theme.font.size.xs,
      }}
    >
      Late interaction skipped: {reason}
    </div>
  );
}
