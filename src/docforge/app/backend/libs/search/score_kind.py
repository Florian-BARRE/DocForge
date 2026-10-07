# ====== Code Summary ======
# ScoreKindClassifier — the pure, store-free classification of what a collection's search score
# represents (cross-encoder rerank vs RRF/DBSF fusion), honouring a run-time rerank degradation.

# ====== Standard Library Imports ======
from collections.abc import Iterator
from typing import Any

# ====== Third-Party Library Imports ======
from loggerplusplus import loggerplusplus

# ====== Internal Project Imports ======
from shared_libs.pipelines.search.nodes.rerank.cross_encoder.core import _RERANK_DEGRADED


class ScoreKindClassifier:
    """Static classification of a collection's delivered search score."""

    logger = loggerplusplus.bind(identifier="ScoreKindClassifier")

    def __new__(cls, *args: object, **kwargs: object) -> None:
        raise TypeError("ScoreKindClassifier is a static-only class and cannot be instantiated.")

    @classmethod
    def __iter_action_blobs(cls, blob: dict[str, Any]) -> Iterator[dict[str, Any]]:
        """Yield every action-node dict in a (possibly nested) group/foreach search blob."""
        # 1. A foreach wraps a single group body; a group holds children — descend into both.
        if "body" in blob:
            yield from cls.__iter_action_blobs(blob["body"])
        elif "nodes" in blob:
            for child in blob["nodes"]:
                yield from cls.__iter_action_blobs(child)
        # 2. A leaf action carries a family — it is what we iterate over.
        elif blob.get("family"):
            yield blob

    @classmethod
    def score_kind(cls, search_blob: dict[str, Any] | None, rerank_degraded: bool = False) -> str:
        """
        Classify what a collection's search score represents, so the client can label it.

        Cheap, store-free blob inspection (no I/O): a rerank node makes the delivered score a
        cross-encoder relevance score; otherwise it is the retrieve node's server-side fusion score
        (RRF by default, DBSF when configured). An empty/None blob is the stock default (RRF).

        The label reflects the ACTUAL score source, not merely the topology: when the rerank stage
        DEGRADED at run time (a slow/cold reranker, so it handed back the fusion-order pool), the
        delivered score is the fusion score — ``rerank_degraded=True`` steps the label back to the
        fusion kind instead of mislabelling a fusion score as a cross-encoder score.

        Args:
            search_blob (dict | None): The collection's stored search blob ({}/None = stock default).
            rerank_degraded (bool): Whether this run's rerank degraded to fusion-order (from the
                run's ``SearchResult.debug`` — see ``rerank_degraded``). Ignored for a blob with no
                rerank node.

        Returns:
            str: One of 'cross_encoder_rerank', 'dbsf_fusion', 'rrf_fusion'.
        """
        # 1. Empty/None → the stock default topology (hybrid retrieve, RRF fusion, no rerank).
        blob = search_blob or {}
        if not blob.get("nodes") and "body" not in blob:
            return "rrf_fusion"
        # 2. A rerank node re-scores the pool → the delivered score is the cross-encoder's — UNLESS
        #    it degraded to fusion-order at run time, in which case the score is the fusion score.
        actions = list(cls.__iter_action_blobs(blob))
        if not rerank_degraded and any(node.get("family") == "rerank" for node in actions):
            return "cross_encoder_rerank"
        # 3. Otherwise the retrieve node's fusion strategy decides (defaults to RRF).
        retrieve = next((node for node in actions if node.get("family") == "retrieve"), None)
        fusion = (retrieve or {}).get("config", {}).get("fusion", "rrf")
        return "dbsf_fusion" if fusion == "dbsf" else "rrf_fusion"

    @classmethod
    def rerank_degraded(cls, debug: dict[str, Any] | None) -> bool:
        """
        Whether the run's rerank stage degraded to fusion-order (its score is a fusion score).

        The rerank node stamps a specific note into ``SearchResult.debug['degraded']`` when it
        gives up on a slow/cold reranker and returns the incoming fusion-order pool. Detecting THAT
        note — distinct from an encode-axis degradation, after which the rerank still truly ran on
        the fused pool — is what lets ``score_kind`` label the delivered score honestly.

        Args:
            debug (dict | None): The run's ``SearchResult.debug`` bag ({}/None = healthy run).

        Returns:
            bool: True when the rerank degrade note is present in the run's degrade trace.
        """
        # 1. The degrade bag joins one or more notes; the rerank marker rides in as a substring.
        note = (debug or {}).get("degraded") or ""
        return _RERANK_DEGRADED in note


__all__ = ["ScoreKindClassifier"]
