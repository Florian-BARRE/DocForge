// ====== Code Summary ======
// The fleet-wide job management page (the "step back and manage" flagship): every job across every
// collection, filterable/sortable/searchable, paginated, plus the SRE observability panels (new-
// failures banner, trends sparklines, failure breakdown) that sit above the triage list itself.
// State (page fetch/poll, worker join, tab/pagination/filters) is split across small hooks; this
// component only lays the page out.

import { useState } from "react";
import type { JobOrder, JobSort } from "../../api/jobs";
import { ErrorState } from "../../components/ErrorState";
import { EmptyState } from "../../components/EmptyState";
import { LoadingState } from "../../components/LoadingState";
import { PageHeader } from "../../components/PageHeader";
import type { Navigate } from "../../shell/view";
import { theme } from "../../theme";
import { FailureBreakdownPanel } from "./FailureBreakdownPanel";
import { EMPTY_JOB_FILTERS, JobFilterBar, type JobFilters } from "./JobFilterBar";
import { JobFleetList } from "./JobFleetList";
import { JobStatusTabs, TAB_STATUS, type JobFleetTab } from "./JobStatusTabs";
import { JobsPager } from "./JobsPager";
import { JobTrendsPanel } from "./JobTrendsPanel";
import { NewFailuresBanner } from "./NewFailuresBanner";
import { useJobsFleetPage } from "./state/useJobsFleetPage";
import { useRunningWorkerMap } from "./state/useRunningWorkerMap";

const PAGE_SIZE = 25;

interface AllJobsPageProps {
  onNavigate: Navigate;
}

/** A UI date-only bound ("yyyy-mm-dd") to the ISO instant the API expects — start/end of that day. */
function toCreatedAfterIso(dateOnly: string): string | undefined {
  return dateOnly ? `${dateOnly}T00:00:00.000Z` : undefined;
}
function toCreatedBeforeIso(dateOnly: string): string | undefined {
  return dateOnly ? `${dateOnly}T23:59:59.999Z` : undefined;
}

export function AllJobsPage({ onNavigate }: AllJobsPageProps) {
  const [tab, setTab] = useState<JobFleetTab>("all");
  const [offset, setOffset] = useState(0);
  const [filters, setFilters] = useState<JobFilters>(EMPTY_JOB_FILTERS);
  const [sort, setSort] = useState<JobSort>("created");
  const [order, setOrder] = useState<JobOrder>("newest");
  const [trendsWindowHours, setTrendsWindowHours] = useState(24);

  const { page, error, patchJob } = useJobsFleetPage({
    status: TAB_STATUS[tab], order, sort, limit: PAGE_SIZE, offset,
    collectionId: filters.collectionId || undefined,
    stage: filters.stage || undefined,
    errorType: filters.errorType || undefined,
    search: filters.search || undefined,
    createdAfter: toCreatedAfterIso(filters.createdAfter),
    createdBefore: toCreatedBeforeIso(filters.createdBefore),
  });
  const workerMap = useRunningWorkerMap();

  const selectTab = (next: JobFleetTab) => {
    setTab(next);
    setOffset(0); // a new filter starts back on its own first page
    setOrder(next === "pending" ? "oldest" : "newest"); // pending reads FIFO; every other tab newest-first
  };

  const applyFilters = (next: JobFilters) => {
    setFilters(next);
    setOffset(0);
  };

  /** A failure-breakdown bucket / the new-failures banner both drop the user straight into a
   *  pre-filtered Failed view — the "why it's breaking, now show me those jobs" loop. */
  const focusFailures = (patch: Partial<JobFilters> = {}) => {
    setTab("failed");
    setOrder("newest");
    setOffset(0);
    setFilters({ ...EMPTY_JOB_FILTERS, ...patch });
  };

  return (
    <div className="df-rise" style={{ padding: theme.space.xl, overflowY: "auto", height: "100%", maxWidth: 1200, margin: "0 auto", width: "100%" }}>
      <PageHeader
        title="All Jobs"
        subtitle="Every ingestion job across every collection — Pending shows what runs next (oldest first)."
      />
      <NewFailuresBanner onViewFailures={() => focusFailures()} />
      <JobTrendsPanel windowHours={trendsWindowHours} onWindowHoursChange={setTrendsWindowHours} />
      <FailureBreakdownPanel
        windowHours={24}
        onSelectErrorType={(errorType) => focusFailures({ errorType })}
        onSelectStage={(stage) => focusFailures({ stage })}
        onSelectCollection={(collectionId) => focusFailures({ collectionId })}
      />
      <div style={{ marginBottom: theme.space.l }}>
        <JobStatusTabs active={tab} onSelect={selectTab} />
      </div>
      <JobFilterBar filters={filters} onFiltersChange={applyFilters} sort={sort} onSortChange={setSort} order={order} onOrderChange={setOrder} />

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
