# ====== Code Summary ======
# IngestPipeline — the root of the ingest pipeline. It holds the ordered stage set (ingest -> parse
# -> enrich -> chunk -> contextualize -> metagen -> embed_index); the engine derives the execution
# order from each stage's input bindings. The stages are built + injected by the assembler (which
# resolves the per-collection config + the live services), so the pipeline itself just carries them.
# Its output is the structural CompositeOutput (the map of every stage's output) — the worker/caller
# reads whichever stage output it needs (e.g. embed_result, or the IR).

# ====== Internal Project Imports ======
from common_libs.pipelines import AbstractNode, CompositeNode, CompositeOutput, NodeKind, NodeSpec

# ====== Local Project Imports ======
from .context import IngestContext
from .errors import IngestError
from .io import IngestInput


class IngestPipeline(CompositeNode):
    """
    The ingest pipeline — runs its (assembler-provided) stages under the engine.

    The assembler builds each stage with its resolved config + registers the live services, then
    constructs the pipeline with the ordered stage set; the engine resolves each stage's input from
    the upstream outputs and runs them in dependency order.
    """

    SPEC = NodeSpec(key="ingest", name="Ingest pipeline", description="Document ingestion pipeline.")
    KIND = NodeKind.PIPELINE
    Input = IngestInput
    Output = CompositeOutput
    Context = IngestContext
    Error = IngestError

    def __init__(self, stages: list[AbstractNode]) -> None:
        """
        Wire the pipeline around its ordered stage set.

        Args:
            stages (list[AbstractNode]): The ingest stages, already built with their config +
                service requirements (the assembler provides them). The engine topo-orders them.
        """
        super().__init__()
        self._stages = stages

    @property
    def children(self) -> list[AbstractNode]:
        """The pipeline's stages (engine-ordered by their input bindings)."""
        return self._stages


__all__ = ["IngestPipeline"]
