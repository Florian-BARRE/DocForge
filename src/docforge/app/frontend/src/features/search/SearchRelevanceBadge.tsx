// ====== Code Summary ======
// Human-readable relevance badge for one hit — a coarse High/Medium/Low bucket PLUS the raw numeric
// score shown by default (in mono, de-emphasized — never the bold accent treatment, so it doesn't
// read as a "% match" it isn't) right next to it. A power user (RAG engineer persona) needs the
// number without an extra click; the bucket stays as the plain-English complement for everyone else.

import { Chip, type ChipTone } from "../../components/Chip";
import { theme } from "../../theme";
import { relevanceBucket } from "./searchRelevance";

/** What the score actually is — a rank-fused signal, not a raw similarity, so it doesn't read
 *  as a plain [0,1] confidence and near-top ties are expected. */
const SCORE_TOOLTIP =
  "Fused rank-based relevance score (Reciprocal Rank Fusion across the searched semantic/lexical " +
  "targets, reranked when the collection has a reranker configured) — higher is better. Not a raw " +
  "similarity, so it is not directly comparable across different queries or target selections.";

const BUCKET_TONE: Record<ReturnType<typeof relevanceBucket>, ChipTone> = {
  // "high"/"medium" borrow the shared status-ink chip tones (never the forge accent — that's
  // reserved for the one active/primary thing, not a per-row at-rest label, per brand.md).
  high: "ok",
  medium: "warn",
  // "low" is deliberately quiet, not the error tone — a weak match isn't a failure.
  low: "dim",
};

const BUCKET_LABEL: Record<ReturnType<typeof relevanceBucket>, string> = {
  high: "High relevance",
  medium: "Medium relevance",
  low: "Low relevance",
};

interface SearchRelevanceBadgeProps {
  score: number;
  topScore: number;
}

export function SearchRelevanceBadge({ score, topScore }: SearchRelevanceBadgeProps) {
  const bucket = relevanceBucket(score, topScore);

  return (
    <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
      <Chip tone={BUCKET_TONE[bucket]} title="Relevance bucket, derived from this result set's top score — not a raw similarity percentage.">
        {BUCKET_LABEL[bucket]}
      </Chip>
      <span
        title={SCORE_TOOLTIP}
        style={{
          fontFamily: theme.font.mono, fontSize: theme.font.size.xs, color: theme.color.dim,
          cursor: "help", whiteSpace: "nowrap",
        }}
      >
        score {score.toFixed(4)}
      </span>
    </div>
  );
}
