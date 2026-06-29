# ====== Code Summary ======
# IngestStageContextualize — the contextualize stage of the ingest pipeline (StageKey.CONTEXTUALIZE).
# It wires its single pure step (no provider chain, no service) around the injected ContextualizeConfig
# and surfaces that step's output as the stage output (contextualized chunks + tally).
# IDEMPOTENT_WRITE: it is never node-cached; idempotency comes from the downstream Postgres/Qdrant
# upserts that consume embed_text.

# ====== Internal Project Imports ======
from common_libs.config.pipeline import ContextualizeConfig
from common_libs.pipelines import CachePolicy, NodeOutput, StageKey, StageSpec

# ====== Local Project Imports ======
from ..base import IngestStageBase
from .context import IngestStageContextualizeContext
from .errors import IngestStageContextualizeError
from .io import IngestStageContextualizeInput, IngestStageContextualizeOutput
from .steps import IngestStageContextualizeStepContextualize


class IngestStageContextualize(IngestStageBase):
    """
    Contextualize stage — build each chunk's embed_text from title + breadcrumb + body.

    Declares its single pure step; the engine runs it and the stage surfaces its output. The
    ContextualizeConfig is an assembly-time constructor arg (not run data), threaded to the step.
    """

    SPEC = StageSpec(
        key=StageKey.CONTEXTUALIZE,
        name="Contextualize",
        description=(
            "Build each chunk's embed_text from the document title, heading breadcrumb, and chunk "
            "body."
        ),
        cache_policy=CachePolicy.IDEMPOTENT_WRITE,
    )
    Input = IngestStageContextualizeInput
    Output = IngestStageContextualizeOutput
    Context = IngestStageContextualizeContext
    Error = IngestStageContextualizeError

    def __init__(self, config: ContextualizeConfig | None = None) -> None:
        """
        Wire the stage around the contextualization config and build its single step.

        Args:
            config (ContextualizeConfig | None): Header-template controls (doc title / breadcrumb
                toggles + separators). When None, a default ``ContextualizeConfig`` is used.
        """
        super().__init__()
        self._config = config if config is not None else ContextualizeConfig()
        self._steps = [IngestStageContextualizeStepContextualize(self._config)]

    @property
    def children(self) -> list:
        """The single contextualize step."""
        return self._steps

    def aggregate(self, child_outputs: dict[str, NodeOutput]) -> IngestStageContextualizeOutput:
        """
        Surface the single step's output as the stage output.

        Args:
            child_outputs (dict[str, NodeOutput]): Step key -> its output.

        Returns:
            IngestStageContextualizeOutput: The contextualized chunks plus the tally.
        """
        # 1. Pull the single step's typed output by its step key.
        contextualized = child_outputs["contextualize"]

        # 2. Surface it as the stage output (chunks + tally).
        return IngestStageContextualizeOutput(
            chunks=contextualized.chunks,
            contextualize_result=contextualized.contextualize_result,
        )


__all__ = ["IngestStageContextualize"]
