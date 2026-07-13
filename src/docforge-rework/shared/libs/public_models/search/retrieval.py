# ====== Code Summary ======
# The retrieval-side flow artefacts: CandidateSet (the raw candidate pool a retriever emits),
# ScoredCandidates (the same pool carrying an aggregate quality score so a rerank node whose OUTPUT
# face is scored can be gated by a ScoreBelow escalation edge), and RankedHits (the hydrated,
# ordered hits the delivery stage turns into the final result). All subclass Artifact and are
# compared by the graph validator through a plain subclass check.
#
# Note: the ScoreBelow escalation is enabled at the NODE's Produces face (which subclasses
# ScoredOutput, in the pipelines layer), not here — public_models is the bottom vocabulary layer
# and must not import upward from pipelines. ScoredCandidates carries the aggregate score field so
# that scored output face has a value to expose. See the Wave-1 report's contract-deviation note.

# ====== Third-Party Library Imports ======
from pydantic import Field

# ====== Internal Project Imports ======
from ..base import Artifact
from .elements import Candidate, Hit


class CandidateSet(Artifact):
    """
    The raw candidate pool a retriever emits — chunk ids + scores, before hydration.

    Attributes:
        candidates (list[Candidate]): The retrieval candidates, best-first as the store returned
            them (the fusion order for a hybrid retriever).
    """

    candidates: list[Candidate] = Field(
        default_factory=list, description="Retrieval candidates, best-first (fusion order)."
    )


class ScoredCandidates(Artifact):
    """
    A candidate pool carrying an aggregate quality score (top-1 candidate score).

    Produced by a fuse/rerank node whose OUTPUT face is scored, so a ``ScoreBelow`` edge can
    escalate to a stronger rerank when the best candidate's score is too low. The aggregate is the
    top-1 candidate score — the strongest signal available before delivery.

    Attributes:
        candidates (list[Candidate]): The scored candidates, best-first.
        score (float): Aggregate quality of the pool — the top-1 candidate score in [0, 1].
    """

    candidates: list[Candidate] = Field(
        default_factory=list, description="The scored candidates, best-first."
    )
    score: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="Aggregate pool quality (top-1 candidate score) a ScoreBelow edge compares.",
    )


class RankedHits(Artifact):
    """
    The hydrated, ordered hits — what the delivery stage packages into the final result.

    Attributes:
        hits (list[Hit]): The hits in delivered order (rank 1 first), each carrying its final
            score, rank and hydrated text/metadata.
    """

    hits: list[Hit] = Field(
        default_factory=list, description="Hydrated hits in delivered order (rank 1 first)."
    )


__all__ = ["CandidateSet", "ScoredCandidates", "RankedHits"]
