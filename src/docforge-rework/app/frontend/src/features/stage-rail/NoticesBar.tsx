// ====== Code Summary ======
// Surfaces what the server did beyond the literal action (dependency cascades, e.g. "disabling
// render also disabled enrich") plus any outstanding validation issues — both MUST be shown,
// never silently swallowed.

import { ApiIssueList } from "../../components/ApiIssueList";
import type { ValidationIssue } from "../../api/types";
import { theme } from "../../theme";

interface NoticesBarProps {
  notices: string[];
  issues: ValidationIssue[];
}

export function NoticesBar({ notices, issues }: NoticesBarProps) {
  if (!notices.length && !issues.length) return null;
  return (
    <div
      style={{
        padding: `${theme.space.s}px ${theme.space.l}px`, borderBottom: `1px solid ${theme.color.line}`,
        display: "flex", flexDirection: "column", gap: theme.space.xs,
      }}
    >
      {notices.map((notice, index) => (
        <div
          key={index}
          style={{
            color: theme.color.accent, background: theme.color.accentSoft, borderRadius: theme.radius.s,
            padding: `${theme.space.xs}px ${theme.space.s}px`, fontSize: theme.font.size.s,
          }}
        >
          ℹ {notice}
        </div>
      ))}
      <ApiIssueList issues={issues} />
    </div>
  );
}
