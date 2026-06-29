# ====== Code Summary ======
# IngestPipeline — the root of the ingest pipeline. In this end-to-end slice it holds the single
# ingest stage; its output is that stage's output. As more stages are added (parse, enrich, chunk…),
# they are appended here and the engine orders them by their input bindings.

# ====== Internal Project Imports ======
from common_libs.pipelines import CompositeNode, NodeKind, NodeOutput, NodeSpec

# ====== Local Project Imports ======
from .context import IngestContext
from .errors import IngestError
from .io import IngestInput, IngestOutput
from .stages.ingest import IngestStageIngest


class IngestPipeline(CompositeNode):
    """
    The ingest pipeline — runs its stages and exposes the terminal stage's output.

    Declares its stages; the engine resolves each stage's input, runs it, and applies its policy.
    """

    SPEC = NodeSpec(key="ingest", name="Ingest pipeline", description="Document ingestion pipeline.")
    KIND = NodeKind.PIPELINE
    Input = IngestInput
    Output = IngestOutput
    Context = IngestContext
    Error = IngestError

    def __init__(self) -> None:
        """Build the pipeline's stages (currently the single ingest stage)."""
        super().__init__()
        self._stages = [IngestStageIngest()]

    @property
    def children(self) -> list:
        """The pipeline's stages."""
        return self._stages

    def aggregate(self, child_outputs: dict[str, NodeOutput]) -> IngestOutput:
        """
        The pipeline output is its terminal stage's output.

        Args:
            child_outputs (dict[str, NodeOutput]): Stage key -> its output.

        Returns:
            IngestOutput: The ingest stage's output.
        """
        return child_outputs["ingest"]


__all__ = ["IngestPipeline"]
