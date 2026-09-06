// ====== Code Summary ======
// The five fleet-status tabs for AllJobsPage — a segmented filter (not distinct panels), same
// pattern as CollectionsToolbar's health filter / Auth Keys' Active-Revoked-All.

import { TabNav } from "../../components/TabNav";
import type { JobStatusValue } from "../../api/jobs";

/** `undefined` = no status filter (the "All" tab). */
export type JobFleetTab = "pending" | "running" | "done" | "failed" | "all";

export const TAB_STATUS: Record<JobFleetTab, JobStatusValue[] | undefined> = {
  pending: ["pending"],
  running: ["running"],
  done: ["done"],
  failed: ["failed"],
  all: undefined,
};

const TABS: { key: JobFleetTab; label: string }[] = [
  { key: "pending", label: "Pending" },
  { key: "running", label: "Running" },
  { key: "done", label: "Done" },
  { key: "failed", label: "Failed" },
  { key: "all", label: "All" },
];

interface JobStatusTabsProps {
  active: JobFleetTab;
  onSelect: (tab: JobFleetTab) => void;
}

export function JobStatusTabs({ active, onSelect }: JobStatusTabsProps) {
  return (
    <TabNav
      tabs={TABS}
      active={active}
      onSelect={onSelect}
      navId="all-jobs-status-filter"
      ariaLabel="Filter jobs by status"
      role="group"
    />
  );
}
