// ====== Code Summary ======
// The three physical stores a collection's footprint spans, plus the neutral steel/muted swatch
// each one renders as — shared between the segmented bar and the per-store breakdown cards so a
// colour always means the same store everywhere on the panel. Forge orange is reserved for the
// single active/primary thing (brand.md) so these three read purely as "chrome at rest".

import type { CollectionStorage, DocumentStorageBreakdown } from "../../../api/collections";
import { theme as t } from "../../../theme";

export type StoreKey = "s3" | "postgres" | "qdrant";

export interface StoreMeta {
  key: StoreKey;
  label: string;
  color: string;
}

export const STORAGE_STORES: StoreMeta[] = [
  { key: "s3", label: "S3", color: t.color.dim },
  { key: "postgres", label: "PostgreSQL", color: t.color.mute },
  { key: "qdrant", label: "Qdrant", color: t.color.lineStrong },
];

/** Reads a store's `{total_bytes, estimated}` off either the collection-level or a per-document
 *  storage payload — both shapes carry the same three store keys. */
export function storeStats(
  source: CollectionStorage | DocumentStorageBreakdown,
  key: StoreKey,
): { totalBytes: number; estimated: boolean } {
  const stats = source[key];
  return { totalBytes: stats.total_bytes, estimated: stats.estimated };
}
