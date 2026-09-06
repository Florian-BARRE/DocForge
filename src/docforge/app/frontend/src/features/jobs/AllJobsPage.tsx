// ====== Code Summary ======
// The fleet-wide job management page (the "step back and manage" flagship): every job across every
// collection, filterable by status, paginated. Pending shows FIFO order (oldest first — "what runs
// next"); every other tab is newest-first. State (page fetch/poll, worker join, tab/pagination) is
// split across two small hooks; this component only lays the page out.

import { useState } from "react";
import { ErrorState } from "../../components/ErrorState";
import { EmptyState } from "../../components/EmptyState";
import { LoadingState } from "../../components/LoadingState";
import { PageHeader } from "../../components/PageHeader";
import type { Navigate } from "../../shell/view";
import { theme } from "../../theme";
import { JobFleetList } from "./JobFleetList";
import { JobStatusTabs, TAB_STATUS, type JobFleetTab } from "./JobStatusTabs";
import { JobsPager } from "./JobsPager";
import { useJobsFleetPage } from "./state/useJobsFleetPage";
import { useRunningWorkerMap } from "./state/useRunningWorkerMap";

const PAGE_SIZE = 25;

interface AllJobsPageProps {
  onNavigate: Navigate;
}

export function AllJobsPage({ onNavigate }: AllJobsPageProps) {
  const [tab, setTab] = useState<JobFleetTab>("pending");
  const [offset, setOffset] = useState(0);

  const order = tab === "pending" ? "oldest" : "newest";
  const { page, error, patchJob } = useJobsFleetPage({ status: TAB_STATUS[tab], order, limit: PAGE_SIZE, offset });
  const workerMap = useRunningWorkerMap();

  const selectTab = (next: JobFleetTab) => {
    setTab(next);
    setOffset(0); // a new filter starts back on its own first page
  };

  return (
    <div className="df-rise" style={{ padding: theme.space.xl, overflowY: "auto", height: "100%", maxWidth: 1200, margin: "0 auto", width: "100%" }}>
      <PageHeader
        title="All Jobs"
        subtitle="Every ingestion job across every collection — Pending shows what runs next (oldest first)."
      />
      <div style={{ marginBottom: theme.space.l }}>
        <JobStatusTabs active={tab} onSelect={selectTab} />
      </div>

      {error && <ErrorState message={error} />}
      {!error && !page && <LoadingState label="loading jobs…" />}
      {!error && page && page.jobs.length === 0 && (
        <EmptyState title="No jobs here" subtitle="Nothing matches this status filter right now." />
      )}
      {!error && page && page.jobs.length > 0 && (
        <>
          <div style={{ marginBottom: theme.space.m }}>
            <JobsPager total={page.total} limit={page.limit} offset={page.offset} onOffsetChange={setOffset} />
          </div>
          <JobFleetList jobs={page.jobs} workerMap={workerMap} onNavigate={onNavigate} onJobUpdated={patchJob} />
        </>
      )}
    </div>
  );
}
