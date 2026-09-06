// ====== Code Summary ======
// Pure bucketing rule turning a hit's raw fused score into a coarse, non-expert-readable relevance
// bucket. The search score is Reciprocal Rank Fusion (optionally reranked) — NOT a normalized
// similarity — so an absolute cutoff (e.g. "score > 0.7 = good") would be meaningless: RRF's scale
// shifts with the number of fused targets and the reranker in play. Bucketing instead relative to
// this result set's OWN top score keeps the rule honest across any query/collection.

export type RelevanceBucket = "high" | "medium" | "low";

/** A hit scoring at least this fraction of the top score still competes closely with the best match. */
const HIGH_RATIO = 0.75;
/** Below this fraction of the top score, a hit reads as a weak/plausible match at best. */
const MEDIUM_RATIO = 0.4;

/**
 * Bucket a hit's score into High/Medium/Low, relative to the top score in its result set.
 *
 * Args:
 *   score: The hit's own fused score.
 *   topScore: The best score in the same result set (typically `hits[0].score`, results are
 *     returned ranked highest-first).
 *
 * Returns:
 *   RelevanceBucket: "high" at >=75% of the top score, "medium" at >=40%, else "low". When the top
 *     score is non-positive (degenerate result set), any positive score is treated as "medium" and
 *     zero/negative as "low" — there is no meaningful ratio to compute.
 */
export function relevanceBucket(score: number, topScore: number): RelevanceBucket {
  if (topScore <= 0) return score > 0 ? "medium" : "low";
  const ratio = score / topScore;
  if (ratio >= HIGH_RATIO) return "high";
  if (ratio >= MEDIUM_RATIO) return "medium";
  return "low";
}
