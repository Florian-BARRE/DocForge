// ====== Code Summary ======
// Renders the backend's normalized issue list (HttpError.issues) — the same card / left-border
// pattern the pipeline studio's IssuesPanel uses for validation issues, reused here for REST
// errors (409 name clashes, 422 schema/pipeline problems).

import type { ApiIssue } from "../api/http";
import { theme } from "../theme";

export function ApiIssueList({ issues }: { issues: ApiIssue[] }) {
  if (!issues.length) return null;
  return (
    <div>
      {issues.map((issue, index) => (
        <div
          key={index}
          style={{
            background: theme.color.card, borderLeft: `3px solid ${theme.color.error}`,
            borderRadius: theme.radius.s, padding: `${theme.space.xs}px ${theme.space.s}px`,
            marginBottom: theme.space.xs, fontSize: theme.font.size.s,
          }}
        >
          {issue.code && <strong>{issue.code}</strong>}
          {issue.location && (
            <div style={{ color: theme.color.dim, fontSize: theme.font.size.xs }}>{issue.location}</div>
          )}
          {issue.message}
        </div>
      ))}
    </div>
  );
}
