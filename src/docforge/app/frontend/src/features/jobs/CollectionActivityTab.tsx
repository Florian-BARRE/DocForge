// ====== Code Summary ======
// Collection scope's Activity tab — a SCOPED mirror of the deployment scope's Activity ▸ Jobs: same
// components (JobStatusTabs, JobFilterBar, JobsPager, JobFleetList), same always-live poll, just
// fixed to this one collection (the Collection facet is hidden — there's nothing to pick, it's
// already this collection). Replaces the old lighter-weight JobsPage so both Activity surfaces read
// as one consistent triage experience (IA redesign W3).

import { useState } from "react";
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
import { QueueDepthTile } from "../monitoring/QueueDepthTile";
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

interface CollectionActivityTabProps {
  collectionId: string;
  onNavigate: Navigate;
}

export function CollectionActivityTab({ collectionId, onNavigate }: CollectionActivityTabProps) {
  const [tab, setTab] = useState<JobFleetTab>("all");
  const [offset, setOffset] = useState(0);
  const [filters, setFilters] = useState<JobFilters>(EMPTY_JOB_FILTERS);
  const [sort, setSort] = useState<JobSort>("created");
  const [order, setOrder] = useState<JobOrder>("newest");

  const { page, error, patchJob } = useJobsFleetPage({
    status: TAB_STATUS[tab], order, sort, limit: PAGE_SIZE, offset, collectionId,
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

  return (
    <div>
      <div style={{ marginBottom: theme.space.l }}>
        <QueueDepthTile collectionId={collectionId} />
      </div>
      <div style={{ marginBottom: theme.space.l }}>
        <JobStatusTabs active={tab} onSelect={selectTab} />
      </div>
      <JobFilterBar
        filters={filters}
        onFiltersChange={applyFilters}
        sort={sort}
        onSortChange={setSort}
        order={order}
        onOrderChange={setOrder}
        hideCollectionFacet
      />

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
