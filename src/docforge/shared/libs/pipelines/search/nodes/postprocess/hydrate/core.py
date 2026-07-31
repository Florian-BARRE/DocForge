# ====== Code Summary ======
# The hydrate node — turns the candidate pool (chunk ids + scores) into delivered Hits: it ranks the
# candidates by score (best first), CUTS to the query's top_k, then asks the bound CollectionReadPort
# for the rich fields (document_id, text, metadata) of ONLY that cut set — so the over-sampled pool is
# never hydrated wholesale. It emits one Hit per hydrated candidate carrying the authoritative rank +
# the candidate's score. A cut candidate whose row has vanished (deleted between search and hydration)
# is dropped, not fatal — so fewer than top_k hits is possible. No direct store import — the port
# arrives via bind().

# ====== Third-Party Library Imports ======
from pydantic import Field

# ====== Internal Project Imports ======
from shared_libs.pipelines.base import NodeConfig, NodeInput, NodeOutput
from shared_libs.pipelines.registry import NodeRegistry
from shared_libs.public_models.search import CandidateSet, Hit, QuerySpec, RankedHits

# ====== Local Project Imports ======
from ...base import PortBackedNode


class PostprocessHydrateConfig(NodeConfig):
    """No knob — hydration always fetches the rich fields of the ranked candidates."""


class PostprocessHydrateConsumes(NodeInput):
    """Input: the candidate pool to rank/cut + the query spec carrying the delivered top_k."""

    candidates: CandidateSet = Field(description="The candidate pool (chunk ids + scores).")
    spec: QuerySpec = Field(description="The normalised query — its top_k caps the delivered set.")


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
        "Ranks the candidate pool by score (best first), cuts to the query's top_k, then asks the "
        "bound CollectionReadPort.hydrate for ONLY that cut set's document_id/text/metadata "
        "(read-only Postgres) — the over-sampled pool is never hydrated wholesale. Emits one Hit per "
        "hydrated candidate in that order, assigning the 1-based rank and carrying the candidate's "
        "score. A cut candidate whose row vanished is dropped (fewer than top_k hits is possible)."
    )
    Config = PostprocessHydrateConfig
    Consumes = PostprocessHydrateConsumes
    Produces = PostprocessHydrateProduces

    async def run(self, data: PostprocessHydrateConsumes) -> PostprocessHydrateProduces:
        """
        Rank the candidate pool, cut to top_k, and hydrate only the cut set.

        Args:
            data (PostprocessHydrateConsumes): The candidate pool + the query spec (its top_k).

        Returns:
            PostprocessHydrateProduces: The ranked, hydrated hits (at most top_k, best first).
        """
        top_k = data.spec.top_k
        # 1. Rank the whole pool by score (best first), then cut to the delivered top_k.
        ordered = sorted(
            data.candidates.candidates, key=lambda candidate: candidate.score, reverse=True
        )[:top_k]

        # 2. Hydrate ONLY the cut set in one read through the injected port (no wholesale hydration).
        hydrated = await self._read_port.hydrate([candidate.chunk_id for candidate in ordered])

        # 3. Emit a Hit per hydrated candidate; a cut candidate with no row is dropped, not fatal.
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
        self.logger.debug(f"Hydrated {len(hits)}/{top_k} hit(s)")
        # Carry the encode-degradation note through to delivery (None on the healthy path).
        return PostprocessHydrateProduces(
            ranked=RankedHits(hits=hits, degraded=data.candidates.degraded)
        )


__all__ = [
    "PostprocessHydrateNode",
    "PostprocessHydrateConfig",
    "PostprocessHydrateConsumes",
    "PostprocessHydrateProduces",
]
