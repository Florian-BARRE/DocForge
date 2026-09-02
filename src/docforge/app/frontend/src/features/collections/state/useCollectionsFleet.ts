// ====== Code Summary ======
// State for the collections list turned fleet dashboard: loads the collection list, then fans out
// TWO cheap per-collection reads concurrently — the live health probe (verdict/parser/vector count/
// last ingest) and a lightweight document-count query — updating each collection's slice
// INDEPENDENTLY as it resolves (progressive card population, never blocked on the slowest one).
// Also owns the toolbar's derived state: text search (by name), a health-status filter, and a sort key.

import { useEffect, useMemo, useState } from "react";
import { getCollectionHealth, listCollections, type Collection, type CollectionHealth } from "../../../api/collections";
import { queryDocuments } from "../../../api/corpus";

export type FleetSortKey = "name" | "health" | "activity";
export type FleetHealthFilter = "all" | "attention" | "empty" | "operational";

/** Worse-first severity rank for the health sort — an unresolved probe sorts last (no signal yet). */
const HEALTH_RANK: Record<CollectionHealth["verdict"] | "unknown", number> = {
  down: 0,
  degraded: 1,
  ingest_unavailable: 1,
  empty: 3,
  operational: 4,
  unknown: 5,
};

interface FleetEntry {
  collection: Collection;
  health: CollectionHealth | null;
  healthError: string | null;
  docCount: number | null;
  docCountError: string | null;
}

function matchesHealthFilter(filter: FleetHealthFilter, health: CollectionHealth | null): boolean {
  if (filter === "all") return true;
  if (health === null) return false; // unresolved probes only ever show under "All".
  if (filter === "operational") return health.verdict === "operational";
  if (filter === "empty") return health.verdict === "empty";
  return health.verdict === "down" || health.verdict === "degraded" || health.verdict === "ingest_unavailable";
}

export function useCollectionsFleet() {
  const [collections, setCollections] = useState<Collection[] | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [healthById, setHealthById] = useState<Record<string, CollectionHealth>>({});
  const [healthErrorById, setHealthErrorById] = useState<Record<string, string>>({});
  const [docCountById, setDocCountById] = useState<Record<string, number>>({});
  const [docCountErrorById, setDocCountErrorById] = useState<Record<string, string>>({});

  const [searchQuery, setSearchQuery] = useState("");
  const [sortKey, setSortKey] = useState<FleetSortKey>("name");
  const [healthFilter, setHealthFilter] = useState<FleetHealthFilter>("all");

  const load = () => {
    setLoadError(null);
    setHealthById({});
    setHealthErrorById({});
    setDocCountById({});
    setDocCountErrorById({});
    listCollections()
      .then(setCollections)
      .catch((e) => setLoadError(e instanceof Error ? e.message : String(e)));
  };
  useEffect(load, []);

  // Fan out the two per-card probes CONCURRENTLY across every collection, each settling
  // independently — a slow/unreachable provider on one collection never stalls the rest of the grid.
  useEffect(() => {
    if (!collections) return;
    for (const c of collections) {
      getCollectionHealth(c.id)
        .then((h) => setHealthById((prev) => ({ ...prev, [c.id]: h })))
        .catch((e) => setHealthErrorById((prev) => ({ ...prev, [c.id]: e instanceof Error ? e.message : String(e) })));
      queryDocuments(c.id, { pagination: { limit: 1, offset: 0 } })
        .then((r) => setDocCountById((prev) => ({ ...prev, [c.id]: r.total })))
        .catch((e) => setDocCountErrorById((prev) => ({ ...prev, [c.id]: e instanceof Error ? e.message : String(e) })));
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps -- fan-out keys off the collection id set only.
  }, [collections]);

  const entries: FleetEntry[] = useMemo(() => {
    if (!collections) return [];
    return collections.map((collection) => ({
      collection,
      health: healthById[collection.id] ?? null,
      healthError: healthErrorById[collection.id] ?? null,
      docCount: docCountById[collection.id] ?? null,
      docCountError: docCountErrorById[collection.id] ?? null,
    }));
  }, [collections, healthById, healthErrorById, docCountById, docCountErrorById]);

  const visibleEntries: FleetEntry[] = useMemo(() => {
    const query = searchQuery.trim().toLowerCase();
    const filtered = entries.filter((e) => {
      if (query && !e.collection.name.toLowerCase().includes(query)) return false;
      return matchesHealthFilter(healthFilter, e.health);
    });

    const rank = (e: FleetEntry) => HEALTH_RANK[e.health?.verdict ?? "unknown"];
    const lastIngest = (e: FleetEntry) => e.health?.search.index.last_ingest_at;

    return [...filtered].sort((a, b) => {
      if (sortKey === "health") {
        const delta = rank(a) - rank(b);
        if (delta !== 0) return delta;
      } else if (sortKey === "activity") {
        const aTime = lastIngest(a), bTime = lastIngest(b);
        if (aTime && bTime) {
          const delta = new Date(bTime).getTime() - new Date(aTime).getTime();
          if (delta !== 0) return delta;
        } else if (aTime && !bTime) return -1;
        else if (!aTime && bTime) return 1;
      }
      return a.collection.name.localeCompare(b.collection.name);
    });
  }, [entries, searchQuery, healthFilter, sortKey]);

  return {
    collections, loadError, load,
    visibleEntries, totalCount: collections?.length ?? 0,
    searchQuery, setSearchQuery,
    sortKey, setSortKey,
    healthFilter, setHealthFilter,
  };
}

export type { FleetEntry };
