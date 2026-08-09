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

/** Reads a store's `{total_bytes, estimated}` off either the collection-level or a per-document
 *  storage payload — both shapes carry the same three store keys. */
export function storeStats(
  source: CollectionStorage | DocumentStorageBreakdown,
  key: StoreKey,
): { totalBytes: number; estimated: boolean } {
  const stats = source[key];
  return { totalBytes: stats.total_bytes, estimated: stats.estimated };
}

/** A store's share of the grand total as a rounded percentage — 0 when there is nothing to divide. */
export function storeSharePercent(totalBytes: number, grandTotalBytes: number): number {
  return grandTotalBytes === 0 ? 0 : Math.round((totalBytes / grandTotalBytes) * 100);
}
