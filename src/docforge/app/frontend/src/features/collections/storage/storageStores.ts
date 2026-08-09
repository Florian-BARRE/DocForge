// ====== Code Summary ======
// The three physical stores a collection's footprint spans, plus the categorical data-viz swatch
// each one renders as (theme.color.store — warm steel / clay terracotta / olive-moss) — shared
// between the segmented bar, the legend and the per-store breakdown cards so a colour always means
// the same store everywhere on the panel. Forge orange stays reserved for the single active/primary
// thing (brand.md); these three are a deliberately distinct warm hue each, not shades of one grey.

import type { CollectionStorage, DocumentStorageBreakdown } from "../../../api/collections";
import { theme as t } from "../../../theme";

export type StoreKey = "s3" | "postgres" | "qdrant";

export interface StoreMeta {
  key: StoreKey;
  label: string;
  color: string;
}

export const STORAGE_STORES: StoreMeta[] = [
  { key: "s3", label: "S3", color: t.color.store.s3 },
  { key: "postgres", label: "PostgreSQL", color: t.color.store.postgres },
  { key: "qdrant", label: "Qdrant", color: t.color.store.qdrant },
];

/** A store's ON-DISK contribution off either the collection-level or a per-document storage payload.
 *  For S3 that is the content-address DEDUPED `physical_unique_bytes` — the bytes actually written to
 *  disk — NOT the logical per-document `total_bytes`, which double-counts a blob shared by several
 *  documents (e.g. the same file uploaded twice) and would push a store's share past 100%. This is
 *  the figure that composes `grand_total_bytes`, so the three stores' shares sum to 100%. PG/Qdrant
 *  have no logical/physical split, so they fall back to `total_bytes`. */
export function storeStats(
  source: CollectionStorage | DocumentStorageBreakdown,
  key: StoreKey,
): { totalBytes: number; estimated: boolean } {
  const stats = source[key];
  const onDisk = "physical_unique_bytes" in stats ? stats.physical_unique_bytes : stats.total_bytes;
  return { totalBytes: onDisk, estimated: stats.estimated };
}

/** A store's share of the grand total as a rounded percentage — 0 when there is nothing to divide. */
export function storeSharePercent(totalBytes: number, grandTotalBytes: number): number {
  return grandTotalBytes === 0 ? 0 : Math.round((totalBytes / grandTotalBytes) * 100);
}
