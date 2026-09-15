// ====== Code Summary ======
// Activity ▸ Failures — the "why is it breaking" home: the new-failures banner, the failure-cause
// breakdown (by error class / stage / collection), and a recent-failed list for a quick glance
// without leaving the tab. Every bucket/banner click routes into Jobs pre-filtered via `onFocusJobs`
// (see JobsFocusRequest) rather than duplicating the triage list here.

import type { Navigate } from "../../shell/view";
import { FailureBreakdownPanel } from "./FailureBreakdownPanel";
import type { JobsFocusRequest } from "./ActivityJobsTab";
import { NewFailuresBanner } from "./NewFailuresBanner";
import { RecentJobsPanel } from "../monitoring/RecentJobsPanel";

const BREAKDOWN_WINDOW_HOURS = 24;

interface ActivityFailuresTabProps {
  onNavigate: Navigate;
  onFocusJobs: (patch: JobsFocusRequest) => void;
}

export function ActivityFailuresTab({ onNavigate, onFocusJobs }: ActivityFailuresTabProps) {
  return (
    <div>
      <NewFailuresBanner onViewFailures={() => onFocusJobs({})} />
      <FailureBreakdownPanel
        windowHours={BREAKDOWN_WINDOW_HOURS}
        onSelectErrorType={(errorType) => onFocusJobs({ errorType })}
        onSelectStage={(stage) => onFocusJobs({ stage })}
        onSelectCollection={(collectionId) => onFocusJobs({ collectionId })}
      />
      <RecentJobsPanel
        title="Recently failed"
        status={["failed"]}
        limit={10}
        emptyLabel="No failed jobs yet."
        onNavigate={onNavigate}
      />
    </div>
  );
}
