// ====== Code Summary ======
// The fleet-wide observability home (deployment scope's "step back and manage" flagship) — one page,
// three sections: Jobs (the triage list), Failures (breakdown + forensics), Trends (sparklines +
// backlog). The active section is URL-driven (`view.tab`, see shell/view.ts), same convention as
// CollectionPipelinePage's Ingestion|Search stage. A cross-section "focus request" (Failures bucket
// click, new-failures banner) stays local page state — see ActivityJobsTab's file summary.

import { useState } from "react";
import { TopContentBar } from "../../shell/TopContentBar";
import type { Navigate } from "../../shell/view";
import { theme } from "../../theme";
import { ActivityFailuresTab } from "./ActivityFailuresTab";
import { ActivityJobsTab, type JobsFocusRequest } from "./ActivityJobsTab";
import { ActivitySectionTabs, type ActivityTab } from "./ActivitySectionTabs";
import { ActivityTrendsTab } from "./ActivityTrendsTab";

interface ActivityPageProps {
  tab: ActivityTab;
  onNavigate: Navigate;
}

const SUBTITLE: Record<ActivityTab, string> = {
  jobs: "Every ingestion job across every collection — Pending shows what runs next (oldest first).",
  failures: "Why the fleet is breaking — cause/stage/collection breakdown and the latest failures.",
  trends: "Hourly throughput, failures and backlog across the whole fleet.",
};

export function ActivityPage({ tab, onNavigate }: ActivityPageProps) {
  const [focusRequest, setFocusRequest] = useState<JobsFocusRequest | null>(null);

  const focusJobs = (patch: JobsFocusRequest) => {
    setFocusRequest(patch);
    onNavigate({ name: "activity", tab: "jobs" });
  };

  return (
    <div className="df-rise" style={{ padding: theme.space.xl, overflowY: "auto", height: "100%", maxWidth: 1200, margin: "0 auto", width: "100%" }}>
      <TopContentBar page="Activity" subtitle={SUBTITLE[tab]} onNavigate={onNavigate} />
      <div style={{ marginBottom: theme.space.l }}>
        <ActivitySectionTabs active={tab} onSelect={(next) => onNavigate({ name: "activity", tab: next })} />
      </div>
      {tab === "jobs" && (
        <ActivityJobsTab
          onNavigate={onNavigate}
          focusRequest={focusRequest}
          onFocusConsumed={() => setFocusRequest(null)}
        />
      )}
      {tab === "failures" && <ActivityFailuresTab onNavigate={onNavigate} onFocusJobs={focusJobs} />}
      {tab === "trends" && <ActivityTrendsTab />}
    </div>
  );
}
