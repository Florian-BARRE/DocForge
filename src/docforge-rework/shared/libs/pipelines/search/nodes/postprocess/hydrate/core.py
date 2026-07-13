# ====== Code Summary ======
# The hydrate node — turns the candidate pool (chunk ids + scores) into delivered Hits: it asks the
# bound CollectionReadPort for each chunk's rich fields (document_id, text, metadata) from Postgres,
# ranks the candidates by score (best first), and emits one Hit per hydrated candidate carrying the
# authoritative rank + the candidate's score. A candidate whose row has vanished (deleted between
# search and hydration) is dropped, not fatal. No direct store import — the port arrives via bind().

# ====== Third-Party Library Imports ======
from pydantic import Field

# ====== Internal Project Imports ======
from shared_libs.pipelines.base import NodeConfig, NodeInput, NodeOutput
from shared_libs.pipelines.registry import NodeRegistry
from shared_libs.public_models.search import CandidateSet, Hit, RankedHits

# ====== Local Project Imports ======
from ...base import PortBackedNode


class PostprocessHydrateConfig(NodeConfig):
    """No knob — hydration always fetches the rich fields of the ranked candidates."""


class PostprocessHydrateConsumes(NodeInput):
    """Input: the candidate pool to hydrate and rank."""

    candidates: CandidateSet = Field(description="The candidate pool (chunk ids + scores).")


class PostprocessHydrateProduces(NodeOutput):
    """Output: the ranked, hydrated hits."""

    ranked: RankedHits = Field(description="The hydrated hits, ranked best-first.")


@NodeRegistry.register("postprocess")
class PostprocessHydrateNode(PortBackedNode):
    """Hydrate the candidate pool's rich fields and rank the hits by score."""

    KIND = "hydrate"
    NAME = "Hydrate hits"
    SUMMARY = "Fetch each candidate's rich fields and rank the hits best-first."
    HOW_IT_WORKS = (
        "Asks the bound CollectionReadPort.hydrate for each candidate's document_id/text/metadata "
        "(read-only Postgres), then emits one Hit per hydrated candidate in descending score order, "
        "assigning the 1-based rank and carrying the candidate's score. Missing rows are dropped."
    )
    Config = PostprocessHydrateConfig
    Consumes = PostprocessHydrateConsumes
    Produces = PostprocessHydrateProduces

    async def run(self, data: PostprocessHydrateConsumes) -> PostprocessHydrateProduces:
        """
        Hydrate and rank the candidates.

        Args:
            data (PostprocessHydrateConsumes): The candidate pool to hydrate.

        Returns:
            PostprocessHydrateProduces: The ranked, hydrated hits.
        """
        candidates = data.candidates.candidates
        # 1. Fetch every candidate's rich fields in one read through the injected port.
        chunk_ids = [candidate.chunk_id for candidate in candidates]
        hydrated = await self._read_port.hydrate(chunk_ids)

        # 2. Rank by score (best first); a candidate with no row is dropped, not fatal.
        ordered = sorted(candidates, key=lambda candidate: candidate.score, reverse=True)
        hits: list[Hit] = []
        for candidate in ordered:
            base = hydrated.get(candidate.chunk_id)
            if base is None:
                self.logger.warning(f"Candidate {candidate.chunk_id} has no chunk row; dropping")
                continue
            hits.append(
                Hit(
                    chunk_id=candidate.chunk_id,
                    document_id=base.document_id,
                    score=candidate.score,
                    rank=len(hits) + 1,
                    text=base.text,
                    metadata=base.metadata,
                )
            )
        self.logger.debug(f"Hydrated {len(hits)}/{len(candidates)} candidate(s)")
        return PostprocessHydrateProduces(ranked=RankedHits(hits=hits))


__all__ = [
    "PostprocessHydrateNode",
    "PostprocessHydrateConfig",
    "PostprocessHydrateConsumes",
    "PostprocessHydrateProduces",
]
