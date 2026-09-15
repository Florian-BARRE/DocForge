// ====== Code Summary ======
// Activity ▸ Jobs — the fleet-wide triage list: every job across every collection, filterable/
// sortable/searchable, paginated. Also accepts a one-shot `focusRequest` from a sibling tab (the
// Failures tab's "why it's breaking, now show me those jobs" loop, or the new-failures banner) — a
// patch of pre-set filters consumed once via effect, then cleared through `onFocusConsumed` so it
// never re-applies on an unrelated re-render.

import { useEffect, useState } from "react";
import type { JobOrder, JobSort } from "../../api/jobs";
import { ErrorState } from "../../components/ErrorState";
import { EmptyState } from "../../components/EmptyState";
import { LoadingState } from "../../components/LoadingState";
import type { Navigate } from "../../shell/view";
import { theme } from "../../theme";
import { EMPTY_JOB_FILTERS, JobFilterBar, type JobFilters } from "./JobFilterBar";
import { JobFleetList } from "./JobFleetList";
import { JobStatusTabs, TAB_STATUS, type JobFleetTab } from "./JobStatusTabs";
import { JobsPager } from "./JobsPager";
import { useJobsFleetPage } from "./state/useJobsFleetPage";
import { useRunningWorkerMap } from "./state/useRunningWorkerMap";

const PAGE_SIZE = 25;

/** A UI date-only bound ("yyyy-mm-dd") to the ISO instant the API expects — start/end of that day. */
function toCreatedAfterIso(dateOnly: string): string | undefined {
  return dateOnly ? `${dateOnly}T00:00:00.000Z` : undefined;
}
function toCreatedBeforeIso(dateOnly: string): string | undefined {
  return dateOnly ? `${dateOnly}T23:59:59.999Z` : undefined;
}

/** A pre-filter request handed down from a sibling section — see the file-level summary. */
export interface JobsFocusRequest {
  errorType?: string;
  stage?: string;
  collectionId?: string;
}

interface ActivityJobsTabProps {
  onNavigate: Navigate;
  focusRequest: JobsFocusRequest | null;
  onFocusConsumed: () => void;
}

export function ActivityJobsTab({ onNavigate, focusRequest, onFocusConsumed }: ActivityJobsTabProps) {
  const [tab, setTab] = useState<JobFleetTab>("all");
  const [offset, setOffset] = useState(0);
  const [filters, setFilters] = useState<JobFilters>(EMPTY_JOB_FILTERS);
  const [sort, setSort] = useState<JobSort>("created");
  const [order, setOrder] = useState<JobOrder>("newest");

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

  // A focus request always lands the user straight into a pre-filtered Failed view, regardless of
  // whichever status tab/pagination the Jobs tab was last left on.
  useEffect(() => {
    if (!focusRequest) return;
    setTab("failed");
    setOrder("newest");
    setOffset(0);
    setFilters({ ...EMPTY_JOB_FILTERS, ...focusRequest });
    onFocusConsumed();
    // eslint-disable-next-line react-hooks/exhaustive-deps -- `onFocusConsumed` is a stable setter-closure from the parent, not a dep that should re-trigger this.
  }, [focusRequest]);

  const selectTab = (next: JobFleetTab) => {
    setTab(next);
    setOffset(0); // a new filter starts back on its own first page
    setOrder(next === "pending" ? "oldest" : "newest"); // pending reads FIFO; every other tab newest-first
  };

  const applyFilters = (next: JobFilters) => {
    setFilters(next);
    setOffset(0);
  };

  return (
    <div>
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
