// ====== Code Summary ======
// Fetches GET /collection-aliases once and indexes the alias names by the collection they point at, so
// the fleet list and the collection header can show "which alias belongs to which collection" without a
// per-collection call (CollectionListItem carries no aliases). Purely decorative data: a failed fetch
// degrades to "no chips" rather than surfacing an error over the page it decorates.

import { useEffect, useState } from "react";
import { listCollectionAliases } from "../../../api/collectionAliases";

/** Alias names keyed by target collection id (empty map while loading or on failure). */
export function useCollectionAliases(): Map<string, string[]> {
  const [byCollection, setByCollection] = useState<Map<string, string[]>>(new Map());

  useEffect(() => {
    let cancelled = false;
    listCollectionAliases()
      .then((aliases) => {
        if (cancelled) return;
        const grouped = new Map<string, string[]>();
        for (const alias of aliases) {
          grouped.set(alias.collection_id, [...(grouped.get(alias.collection_id) ?? []), alias.name]);
        }
        setByCollection(grouped);
      })
      .catch(() => undefined);
    return () => { cancelled = true; };
  }, []);

  return byCollection;
}
