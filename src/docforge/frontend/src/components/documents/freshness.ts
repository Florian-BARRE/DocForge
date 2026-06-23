// ====== Code Summary ======
// Pure helper for document freshness — decides whether a document is stale
// (its pipeline version no longer matches the collection's pipeline version)
// and therefore needs re-indexing.

/**
 * Determine whether a document is stale relative to its collection.
 *
 * A document is considered stale when both pipeline versions are known and
 * differ — meaning the collection config changed after the document was
 * ingested, so the document should be re-indexed to reflect the new pipeline.
 *
 * When either version is missing (null/undefined) we deliberately return
 * `false`: without complete information we never flag a document as stale.
 *
 * Args:
 *   docPipelineVersion: The document's pipeline version, or null/undefined.
 *   collectionPipelineVersion: The collection's current pipeline version,
 *     or null/undefined.
 *
 * Returns:
 *   `true` when both versions are defined and different; otherwise `false`.
 */
export function isDocStale(
  docPipelineVersion: string | null | undefined,
  collectionPipelineVersion: string | null | undefined,
): boolean {
  // 1. Bail out when either side lacks version info — never guess staleness.
  if (docPipelineVersion == null || collectionPipelineVersion == null) {
    return false
  }

  // 2. Stale only when the two known versions disagree.
  return docPipelineVersion !== collectionPipelineVersion
}
