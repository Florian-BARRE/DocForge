// ====== Code Summary ======
// Shown when a reingest was refused 422 `replay_unsupported`: the server's reason plus the stages
// it WOULD accept, each as a one-click choice (and always "Full re-ingest"). Choosing only updates
// the caller's selection — the user re-submits deliberately.

import type { ReplayUnsupported } from "../../api/reingest";
import { theme } from "../../theme";
import { Button } from "../Button";

interface ReplayUnsupportedNoticeProps {
  issue: ReplayUnsupported;
  onPick: (stage: string | null) => void;
}

export function ReplayUnsupportedNotice({ issue, onPick }: ReplayUnsupportedNoticeProps) {
  return (
    <div role="alert" style={{ display: "flex", flexDirection: "column", gap: theme.space.xs, fontSize: theme.font.size.s }}>
      <span style={{ color: theme.color.errorStrong }}>{issue.reason}</span>
      <span style={{ display: "flex", flexWrap: "wrap", alignItems: "center", gap: theme.space.xs }}>
        <span style={{ color: theme.color.dim }}>
          {issue.allowed.length > 0 ? "Allowed stages:" : "No stage can be replayed yet — run a full re-ingest first."}
        </span>
        {issue.allowed.map((stage) => (
          <Button key={stage} size="sm" onClick={() => onPick(stage)}>
            <span style={{ fontFamily: theme.font.mono }}>{stage}</span>
          </Button>
        ))}
        <Button size="sm" onClick={() => onPick(null)}>Full re-ingest</Button>
      </span>
    </div>
  );
}
