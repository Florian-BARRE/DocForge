# ====== Code Summary ======
# SearchTuning — the per-request knobs that tune ONE search run without touching the collection's
# stored search blob: a min_score cut on the final ranking, a rerank skip/require, and a fusion
# override. It turns the knobs into the reserved QuerySpec.flags the pure nodes read (run-input data),
# checks a rerank=True request against the resolved blob (a graph without a rerank stage cannot honour
# it — a caller error, never silently ignored), and relabels the response's score_kind to what the run
# actually delivered.

# ====== Standard Library Imports ======
from collections.abc import Sequence
from dataclasses import dataclass, replace
from typing import Any

# ====== Internal Project Imports ======
from shared_libs.public_models.search import CONTENT_FIELD, FUSION_FLAG, RERANK_FLAG, SearchTarget

# The score_kind label of a cross-encoder-reranked score (fusion kinds are "<strategy>_fusion").
_RERANK_KIND = "cross_encoder_rerank"


class SearchTuningError(ValueError):
    """Raised when a tuning knob cannot be honoured by the collection's search graph (→ 422)."""


@dataclass(frozen=True, slots=True)
class SearchTuning:
    """
    The per-request tuning of one search run (all None/False = the stored graph, unchanged).

    Attributes:
        min_score (float | None): Drop final hits scoring below this; None = no threshold.
        rerank (bool | None): False skips the rerank stage, True requires one; None = the blob.
        fusion (str | None): "rrf" / "dbsf" overrides the retrieve node's fusion; None = the blob.
        debug (bool): Surface each hit's fusion/rerank scores.
    """

    min_score: float | None = None
    rerank: bool | None = None
    fusion: str | None = None
    debug: bool = False

    @staticmethod
    def __families(blob: dict[str, Any]) -> set[str]:
        """Collect every action-node family of a (possibly nested) group/foreach blob."""
        # 1. A foreach wraps one body, a group holds nodes; a leaf action carries its family.
        if "body" in blob:
            return SearchTuning.__families(blob["body"])
        if "nodes" in blob:
            return {family for child in blob["nodes"] for family in SearchTuning.__families(child)}
        return {blob["family"]} if blob.get("family") else set()

    def for_targets(self, targets: Sequence[SearchTarget] | None) -> "SearchTuning":
        """
        Skip the rerank when every target is metadata-only (unless the caller required it).

        The cross-encoder scores the chunk BODY against the query; on a metadata-only search the
        ranking is the field match, which a body re-score would override with an irrelevant one.

        Args:
            targets (Sequence[SearchTarget] | None): The request's targets (None/empty = content).

        Returns:
            SearchTuning: ``rerank=False`` for a metadata-only search left at the blob default;
                this tuning unchanged otherwise.
        """
        meta_only = bool(targets) and all(t.field != CONTENT_FIELD for t in targets or ())
        return replace(self, rerank=False) if meta_only and self.rerank is None else self

    def flags(self) -> dict[str, Any]:
        """
        The reserved QuerySpec.flags this tuning sets (empty for an untuned request).

        Returns:
            dict[str, Any]: ``{rerank: False}`` when the stage is skipped, ``{fusion: <strategy>}``
            when the fusion is overridden. rerank=True needs no flag (the stage runs as stored).
        """
        # 1. Only the deviations from the stored graph ride as flags — the default run is untouched.
        flags: dict[str, Any] = {}
        if self.rerank is False:
            flags[RERANK_FLAG] = False
        if self.fusion is not None:
            flags[FUSION_FLAG] = self.fusion
        return flags

    def check_blob(self, blob: dict[str, Any]) -> None:
        """
        Reject a rerank=True request on a search graph that has no rerank stage.

        Args:
            blob (dict[str, Any]): The resolved search blob the run will execute.

        Raises:
            SearchTuningError: rerank=True but the graph holds no ``rerank``-family node.
        """
        # 1. Requiring a stage the graph does not have is a caller error, never silently ignored.
        if self.rerank is True and "rerank" not in self.__families(blob):
            raise SearchTuningError(
                "rerank=true but this collection's search pipeline has no rerank stage — enable "
                "reranking in its search pipeline, or omit rerank."
            )

    def score_kind(self, stored_kind: str, fusion_kind: str, raw_kind: str | None = None) -> str:
        """
        Relabel the response score_kind to what this tuned run actually delivered.

        Args:
            stored_kind (str): The label the stored graph yields (rerank degrade already folded in).
            fusion_kind (str): The stored graph's fusion label, as if no rerank had run.
            raw_kind (str | None): The raw-score label when the retrieval queried ONE vector (no
                fusion ran — see ``ScoreKindClassifier.raw_kind``); None when it fused branches.

        Returns:
            str: The rerank label when a rerank actually re-scored the hits; else the raw label when
            no fusion ran; else the fusion label, with the fusion override applied.
        """
        # 1. A rerank that ran stays the rerank label; a skipped one falls back to the retrieval's.
        if stored_kind == _RERANK_KIND and self.rerank is not False:
            return stored_kind
        # 2. One vector queried directly → its raw score (a fusion override had nothing to fuse).
        if raw_kind is not None:
            return raw_kind
        # 3. The fusion override names the fusion strategy that actually ran.
        return f"{self.fusion}_fusion" if self.fusion is not None else fusion_kind


__all__ = ["SearchTuning", "SearchTuningError"]
