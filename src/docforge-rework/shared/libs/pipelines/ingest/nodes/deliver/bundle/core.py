# ====== Code Summary ======
# The bundle node — the LAST node of every ingestion pipeline: it gathers everything the run
# produced into the RunBundle, the pipeline's output contract. Pure assembly (no model call, no
# storage): the graph stays pure, the worker consumes exactly one typed artefact. Wiring it is
# what makes a graph an INGESTION pipeline — the runner refuses a run whose final output is not
# a RunBundle.

# ====== Third-Party Library Imports ======
from pydantic import Field

# ====== Internal Project Imports ======
from shared_libs.pipelines.base import ActionNode, NodeConfig, NodeInput, NodeOutput
from shared_libs.pipelines.registry import NodeRegistry
from shared_libs.public_models import (
    Chunk,
    ChunkEmbeddings,
    DocumentIR,
    GeneratedDocumentMeta,
    IntakeResult,
    PageRenders,
    RunBundle,
)


class BundleConfig(NodeConfig):
    """bundle has no knob — it is a pure assembly of the run's outputs."""


class BundleConsumes(NodeInput):
    """Input: every persistable artefact of the run, bound from its producing stage."""

    ingest: IntakeResult = Field(description="The intake facts (source hash, PDF, page count).")
    ir: DocumentIR = Field(
        description="The document IR — enriched (after enrich_apply) or raw (no enrich stage)."
    )
    pages: PageRenders | None = Field(
        default=None,
        description="The full-page renders — leave unbound when the pipeline has no render stage.",
    )
    chunks: list[Chunk] = Field(
        default_factory=list,
        description="The FINAL chunks (context and generated_meta aboard).",
    )
    document_meta: GeneratedDocumentMeta | None = Field(
        default=None,
        description="Document-scope generated values — leave unbound without a metagen stage.",
    )
    embeddings: ChunkEmbeddings | None = Field(
        default=None,
        description="The chunk vectors — leave unbound without an embed stage (no Qdrant index).",
    )


class BundleProduces(NodeOutput):
    """Output: the run's single delivery — what the worker persists."""

    bundle: RunBundle = Field(description="Everything the run produced, in one typed artefact.")


@NodeRegistry.register("deliver")
class BundleNode(ActionNode):
    """Close the pipeline: assemble the run's outputs into its delivery contract."""

    KIND = "bundle"
    NAME = "Run bundle"
    SUMMARY = "Assemble everything the run produced into the pipeline's output contract."
    HOW_IT_WORKS = (
        "Gathers the intake facts, the enriched IR, the page renders, the final chunks, the "
        "document metadata and the vectors into ONE RunBundle. Pure assembly — wiring this node "
        "last is what makes the graph an ingestion pipeline the worker can persist."
    )
    Config = BundleConfig
    Consumes = BundleConsumes
    Produces = BundleProduces
    UNIQUE_IN_GRAPH = True

    async def run(self, data: BundleConsumes) -> BundleProduces:
        """
        Assemble the delivery.

        Args:
            data (BundleConsumes): The run's persistable artefacts.

        Returns:
            BundleProduces: The RunBundle the worker persists.
        """
        # 1. Pure assembly — the artefacts pass through untouched.
        return BundleProduces(
            bundle=RunBundle(
                ingest=data.ingest,
                ir=data.ir,
                pages=data.pages,
                chunks=data.chunks,
                document_meta=data.document_meta,
                embeddings=data.embeddings,
            )
        )


__all__ = ["BundleNode", "BundleConfig", "BundleConsumes", "BundleProduces"]
