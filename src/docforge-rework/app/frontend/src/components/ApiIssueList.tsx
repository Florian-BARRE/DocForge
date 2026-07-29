// ====== Code Summary ======
// Renders the backend's normalized issue list (HttpError.issues) — a stack of left-accented
// cards, reused for REST errors (409 name clashes, 422 schema/pipeline problems).

import type { ApiIssue } from "../api/http";
import { theme } from "../theme";

export function ApiIssueList({ issues }: { issues: ApiIssue[] }) {
  if (!issues.length) return null;
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: theme.space.xs }}>
      {issues.map((issue, index) => (
        <div
          key={index}
          style={{
            background: theme.color.errorSoft, borderLeft: `3px solid ${theme.color.error}`,
            borderRadius: theme.radius.s, padding: `${theme.space.s}px ${theme.space.m}px`,
            fontSize: theme.font.size.s, color: theme.color.text,
          }}
        >
          {issue.code && (
            <strong style={{ fontFamily: theme.font.mono, color: theme.color.error, fontSize: theme.font.size.xs }}>
              {issue.code}
            </strong>
          )}
          {issue.location && (
            <div style={{ color: theme.color.dim, fontSize: theme.font.size.xs, fontFamily: theme.font.mono, marginTop: 1 }}>
              {issue.location}
            </div>
          )}
          <div>{issue.message}</div>
        </div>
      ))}
    </div>
  );
}
