// ====== Code Summary ======
// The fleet dashboard's toolbar — a name search box, a health-status filter (segmented, reuses
// TabNav's `role="group"` filter mode like Auth Keys' Active/Revoked/All), and a sort-key select.
// Pure controlled inputs; all the actual filtering/sorting logic lives in useCollectionsFleet.

import { inputStyle } from "../../components/inputStyle";
import { TabNav } from "../../components/TabNav";
import { theme as t } from "../../theme";
import type { FleetHealthFilter, FleetSortKey } from "./state/useCollectionsFleet";

const HEALTH_FILTER_TABS: { key: FleetHealthFilter; label: string }[] = [
  { key: "all", label: "All" },
  { key: "attention", label: "Needs attention" },
  { key: "empty", label: "Empty" },
  { key: "operational", label: "Operational" },
];

const SORT_LABEL: Record<FleetSortKey, string> = {
  name: "Name",
  health: "Health (worst first)",
  activity: "Activity (most recent first)",
};

interface CollectionsToolbarProps {
  searchQuery: string;
  onSearchQueryChange: (value: string) => void;
  healthFilter: FleetHealthFilter;
  onHealthFilterChange: (value: FleetHealthFilter) => void;
  sortKey: FleetSortKey;
  onSortKeyChange: (value: FleetSortKey) => void;
  visibleCount: number;
  totalCount: number;
}

export function CollectionsToolbar({
  searchQuery, onSearchQueryChange, healthFilter, onHealthFilterChange, sortKey, onSortKeyChange,
  visibleCount, totalCount,
}: CollectionsToolbarProps) {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: t.space.m, marginBottom: t.space.l }}>
      <div style={{ display: "flex", alignItems: "center", gap: t.space.m, flexWrap: "wrap" }}>
        <input
          type="search"
          placeholder="Search collections by name…"
          value={searchQuery}
          onChange={(e) => onSearchQueryChange(e.target.value)}
          aria-label="Search collections by name"
          style={{ ...inputStyle, maxWidth: 280 }}
        />
        <label style={{ display: "flex", alignItems: "center", gap: t.space.s, fontSize: t.font.size.m, color: t.color.dim }}>
          Sort
          <select
            value={sortKey}
            onChange={(e) => onSortKeyChange(e.target.value as FleetSortKey)}
            aria-label="Sort collections by"
            style={{ ...inputStyle, width: "auto" }}
          >
            {(Object.keys(SORT_LABEL) as FleetSortKey[]).map((key) => (
              <option key={key} value={key}>{SORT_LABEL[key]}</option>
            ))}
          </select>
        </label>
        {totalCount > 0 && (
          <span style={{ marginLeft: "auto", color: t.color.mute, fontSize: t.font.size.s }}>
            {visibleCount} of {totalCount} shown
          </span>
        )}
      </div>
      <TabNav
        tabs={HEALTH_FILTER_TABS}
        active={healthFilter}
        onSelect={onHealthFilterChange}
        navId="collections-health-filter"
        ariaLabel="Filter collections by health"
        role="group"
      />
    </div>
  );
}
