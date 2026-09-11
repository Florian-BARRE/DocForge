// ====== Code Summary ======
// The All Jobs triage bar — id/doc search, collection/stage/error-class facets, a created-at date
// range, and the sort dimension + direction. Every non-default facet is surfaced as an accent "N
// filters active" pill with a one-click Clear, so the active filter state is always visible (per the
// SRE persona's "state invisible" finding) — mirrors CollectionsToolbar's toolbar layout.

import { useEffect, useState } from "react";
import { listCollections } from "../../api/collections";
import type { JobOrder, JobSort } from "../../api/jobs";
import { Button } from "../../components/Button";
import { DateInput } from "../../components/DateInput";
import { inputStyle } from "../../components/inputStyle";
import { theme } from "../../theme";

const SORT_LABEL: Record<JobSort, string> = { created: "Created", duration: "Duration", status: "Status" };
const ORDER_LABEL: Record<JobSort, Record<JobOrder, string>> = {
  created: { newest: "Newest first", oldest: "Oldest first" },
  duration: { newest: "Longest first", oldest: "Shortest first" },
  status: { newest: "Z → A", oldest: "A → Z" },
};

export interface JobFilters {
  search: string;
  collectionId: string;
  stage: string;
  errorType: string;
  createdAfter: string;
  createdBefore: string;
}

export const EMPTY_JOB_FILTERS: JobFilters = {
  search: "", collectionId: "", stage: "", errorType: "", createdAfter: "", createdBefore: "",
};

interface JobFilterBarProps {
  filters: JobFilters;
  onFiltersChange: (next: JobFilters) => void;
  sort: JobSort;
  onSortChange: (next: JobSort) => void;
  order: JobOrder;
  onOrderChange: (next: JobOrder) => void;
}

function activeFacetCount(filters: JobFilters): number {
  return Object.values(filters).filter((v) => v !== "").length;
}

export function JobFilterBar({ filters, onFiltersChange, sort, onSortChange, order, onOrderChange }: JobFilterBarProps) {
  const [collections, setCollections] = useState<{ id: string; name: string }[]>([]);

  useEffect(() => {
    // Best-effort: an empty/failed collection list only degrades the facet to "no options", never
    // blocks the rest of the triage bar.
    listCollections().then((rows) => setCollections(rows.map((c) => ({ id: c.id, name: c.name })))).catch(() => {});
  }, []);

  const set = <K extends keyof JobFilters>(key: K, value: JobFilters[K]) => onFiltersChange({ ...filters, [key]: value });
  const activeCount = activeFacetCount(filters);

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: theme.space.s, marginBottom: theme.space.l }}>
      <div style={{ display: "flex", flexWrap: "wrap", alignItems: "flex-end", gap: theme.space.m }}>
        <label style={{ display: "flex", flexDirection: "column", gap: 4, fontSize: theme.font.size.xs, color: theme.color.dim }}>
          Search (job/doc id)
          <input
            type="search"
            placeholder="paste a full id or a leading fragment…"
            value={filters.search}
            onChange={(e) => set("search", e.target.value)}
            aria-label="Search jobs by job or document id"
            style={{ ...inputStyle, width: 220, fontFamily: theme.font.mono, fontSize: theme.font.size.s }}
          />
        </label>
        <label style={{ display: "flex", flexDirection: "column", gap: 4, fontSize: theme.font.size.xs, color: theme.color.dim }}>
          Collection
          <select
            value={filters.collectionId}
            onChange={(e) => set("collectionId", e.target.value)}
            aria-label="Filter jobs by collection"
            style={{ ...inputStyle, width: 180 }}
          >
            <option value="">All collections</option>
            {collections.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
          </select>
        </label>
        <label style={{ display: "flex", flexDirection: "column", gap: 4, fontSize: theme.font.size.xs, color: theme.color.dim }}>
          Stage
          <input
            value={filters.stage}
            onChange={(e) => set("stage", e.target.value)}
            placeholder="e.g. embed"
            aria-label="Filter jobs by current stage"
            style={{ ...inputStyle, width: 140, fontFamily: theme.font.mono, fontSize: theme.font.size.s }}
          />
        </label>
        <label style={{ display: "flex", flexDirection: "column", gap: 4, fontSize: theme.font.size.xs, color: theme.color.dim }}>
          Error class
          <input
            value={filters.errorType}
            onChange={(e) => set("errorType", e.target.value)}
            placeholder="e.g. TimeoutError"
            aria-label="Filter jobs by error class"
            style={{ ...inputStyle, width: 160, fontFamily: theme.font.mono, fontSize: theme.font.size.s }}
          />
        </label>
        <label style={{ display: "flex", flexDirection: "column", gap: 4, fontSize: theme.font.size.xs, color: theme.color.dim }}>
          Created from
          <DateInput value={filters.createdAfter} onChange={(v) => set("createdAfter", v)} ariaLabel="Created from" />
        </label>
        <label style={{ display: "flex", flexDirection: "column", gap: 4, fontSize: theme.font.size.xs, color: theme.color.dim }}>
          Created to
          <DateInput value={filters.createdBefore} onChange={(v) => set("createdBefore", v)} ariaLabel="Created to" />
        </label>
      </div>
      <div style={{ display: "flex", flexWrap: "wrap", alignItems: "center", gap: theme.space.m }}>
        <label style={{ display: "flex", alignItems: "center", gap: theme.space.s, fontSize: theme.font.size.m, color: theme.color.dim }}>
          Sort
          <select
            value={sort}
            onChange={(e) => onSortChange(e.target.value as JobSort)}
            aria-label="Sort jobs by"
            style={{ ...inputStyle, width: "auto" }}
          >
            {(Object.keys(SORT_LABEL) as JobSort[]).map((key) => <option key={key} value={key}>{SORT_LABEL[key]}</option>)}
          </select>
        </label>
        <Button
          size="sm"
          variant="ghost"
          aria-label="Toggle sort direction"
          onClick={() => onOrderChange(order === "newest" ? "oldest" : "newest")}
        >
          {ORDER_LABEL[sort][order]}
        </Button>
        {activeCount > 0 && (
          <>
            <span
              style={{
                color: theme.color.accentSafe, background: theme.color.accentSoft, border: `1px solid ${theme.color.accentLine}`,
                borderRadius: theme.radius.pill, padding: "2px 10px", fontSize: theme.font.size.xs, fontWeight: theme.font.weight.semibold,
              }}
            >
              {activeCount} filter{activeCount === 1 ? "" : "s"} active
            </span>
            <Button size="sm" variant="ghost" onClick={() => onFiltersChange(EMPTY_JOB_FILTERS)}>Clear</Button>
          </>
        )}
      </div>
    </div>
  );
}
