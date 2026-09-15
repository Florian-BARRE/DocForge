// ====== Code Summary ======
// The Activity page's own section tabs — Jobs (the triage list) / Failures (breakdown + forensics) /
// Trends (sparklines + backlog). Unlike JobStatusTabs (a segmented FILTER over one list, `role="group"`),
// these switch between three genuinely distinct panels, so this stays a real ARIA tablist.

import { TabNav } from "../../components/TabNav";
import type { View } from "../../shell/view";

export type ActivityTab = NonNullable<Extract<View, { name: "activity" }>["tab"]>;

const TABS: { key: ActivityTab; label: string }[] = [
  { key: "jobs", label: "Jobs" },
  { key: "failures", label: "Failures" },
  { key: "trends", label: "Trends" },
];

interface ActivitySectionTabsProps {
  active: ActivityTab;
  onSelect: (tab: ActivityTab) => void;
}

export function ActivitySectionTabs({ active, onSelect }: ActivitySectionTabsProps) {
  return (
    <TabNav
      tabs={TABS}
      active={active}
      onSelect={onSelect}
      navId="activity-sections"
      ariaLabel="Activity sections"
    />
  );
}
