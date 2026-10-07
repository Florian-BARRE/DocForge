# ====== Code Summary ======
# The atomic value objects of the search data-plane: a Candidate (a scored chunk id fresh out of
# retrieval, before hydration) and a Hit (a hydrated, ranked chunk ready for delivery). Both are
# plain BaseModels — they are carried INSIDE the flow artefacts (CandidateSet, RankedHits), never
# bound to a slot on their own, so they need no Artifact identity of their own.

# ====== Third-Party Library Imports ======
from pydantic import BaseModel, ConfigDict, Field


class Candidate(BaseModel):
    """
    One retrieval candidate — a chunk id with its raw retrieval score, before hydration.

    Attributes:
        chunk_id (str): The candidate chunk's id (the key the hydration step looks up).
        score (float): The raw retrieval score (fusion/rerank score, provider-defined scale).
        source (str): Which retrieval branch produced it (e.g. ``"hybrid"``, ``"dense"``) —
            provenance for debugging and for a later fusion step.
        payload (dict | None): Optional raw payload returned by the store (lean vector fields),
            kept for debugging; None when the retriever returned ids + scores only.
        fusion_score (float | None): The pre-rerank fusion score, kept by a rerank stage before it
            overwrites ``score``; None when the candidate was never reranked.
    """

    model_config = ConfigDict(extra="forbid")

    chunk_id: str = Field(description="The candidate chunk's id (the hydration lookup key).")
    score: float = Field(
        description="Raw retrieval score on the provider's scale (higher is better)."
    )
    source: str = Field(description="The retrieval branch that produced it (hybrid/dense/sparse…).")
    payload: dict | None = Field(
        default=None,
        description="Optional raw store payload (lean vector fields), kept for debugging.",
    )
    fusion_score: float | None = Field(
        default=None,
        description="The retrieval (fusion) score this candidate carried BEFORE a rerank stage "
        "overwrote ``score``; None when no rerank re-scored it (``score`` is then the fusion score).",
    )


class Hit(BaseModel):
    """
    One hydrated, ranked search hit — the client-facing unit inside RankedHits/SearchResult.

    Attributes:
        chunk_id (str): The hit chunk's id.
        document_id (str): The id of the document the chunk belongs to.
        score (float): The final score that decided the ranking (carried from the candidate).
        rank (int): 1-based position in the delivered ordering (1 = best).
        text (str | None): The chunk's hydrated text; None when hydration returned metadata only.
        metadata (dict | None): The chunk's hydrated rich metadata; None when not requested.
        fusion_score (float | None): The hit's retrieval (fusion) score (debug provenance).
        rerank_score (float | None): The hit's rerank score when it was reranked, else None.
    """

    model_config = ConfigDict(extra="forbid")

    chunk_id: str = Field(description="The hit chunk's id.")
    document_id: str = Field(description="Id of the document the chunk belongs to.")
    score: float = Field(
        default=0.0, description="Final ranking score (carried from the candidate)."
    )
    rank: int = Field(default=0, description="1-based rank in the delivered ordering (1 = best).")
    text: str | None = Field(
        default=None, description="The chunk's hydrated text (None if omitted)."
    )
    metadata: dict | None = Field(
        default=None, description="The chunk's hydrated rich metadata (None if not requested)."
    )
    fusion_score: float | None = Field(
        default=None,
        description="The retrieval (fusion) score of the hit — equal to ``score`` when no rerank "
        "re-scored it. None when the producer did not record it.",
    )
    rerank_score: float | None = Field(
        default=None,
        description="The rerank (cross-encoder) score when a rerank stage re-scored the hit (then "
        "equal to ``score``); None when it was not reranked.",
    )


__all__ = ["Candidate", "Hit"]
