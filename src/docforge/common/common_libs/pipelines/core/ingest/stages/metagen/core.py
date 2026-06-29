# ====== Code Summary ======
# IngestStageMetagen — the metagen stage of the ingest pipeline (StageKey.METAGEN). It generates
# LLM-derived metadata per chunk (chunk-scope ``derived_meta``) and per document (document-scope
# ``doc_fields``), then assembles the merged ``doc_meta`` the embed/index stage consumes. It assembles
# its four steps (budget_gate -> chunk_scope/doc_scope -> assemble_doc_meta; the engine derives that
# order from their input bindings) and aggregates their outputs into IngestStageMetagenOutput. The
# generation targets + field-type lookup are constructor (assembly) args; the LLM chain + provider
# cache are injected SERVICES the steps declare. An empty chain or no targets is a complete no-op.
# IDEMPOTENT_WRITE: the stage is never node-cached (per-call dedup comes from the provider cache).

# ====== Internal Project Imports ======
from common_libs.config.pipeline.stages.metagen_config import MetaGenTarget
from common_libs.domain import MetaFieldSpec
from common_libs.pipelines import CachePolicy, NodeOutput, StageKey, StageSpec

# ====== Local Project Imports ======
from ..base import IngestStageBase
from .context import IngestStageMetagenContext
from .errors import IngestStageMetagenError
from .io import IngestStageMetagenInput, IngestStageMetagenOutput
from .steps import (
    IngestStageMetagenStepAssembleDocMeta,
    IngestStageMetagenStepBudgetGate,
    IngestStageMetagenStepChunkScope,
    IngestStageMetagenStepDocScope,
)


class IngestStageMetagen(IngestStageBase):
    """
    Metagen stage — generate per-chunk / per-document LLM metadata and assemble doc_meta.

    Declares its four steps; the engine orders + runs them and the stage aggregates their outputs.
    The targets + field-type lookup are provided at assembly (constructor args); the LLM chain and
    provider cache are injected services consumed by the steps.
    """

    SPEC = StageSpec(
        key=StageKey.METAGEN,
        name="Metagen",
        description=(
            "Generate LLM-derived metadata per chunk (derived_meta) and per document (doc_fields), "
            "then assemble the merged doc_meta."
        ),
        cache_policy=CachePolicy.IDEMPOTENT_WRITE,
    )
    Input = IngestStageMetagenInput
    Output = IngestStageMetagenOutput
    Context = IngestStageMetagenContext
    Error = IngestStageMetagenError

    def __init__(
        self,
        targets: list[MetaGenTarget],
        field_types: dict[str, MetaFieldSpec],
        max_concurrency: int = 8,
        max_budget_usd: float = 0.0,
    ) -> None:
        """
        Build the four metagen steps with their assembly-time config.

        Args:
            targets (list[MetaGenTarget]): Field bindings ``{field, prompt, scope}``; empty disables
                the stage (every step becomes a no-op passthrough).
            field_types (dict[str, MetaFieldSpec]): Resolved type lookup for the generated fields,
                keyed by field name. Targets whose field is absent are ignored.
            max_concurrency (int): Maximum concurrent chunk-scope LLM calls.
            max_budget_usd (float): Estimated-cost cap per document (0 = unlimited).
        """
        # 1. Keep the assembly config so parity checks / describe can reach it.
        super().__init__()
        self._targets = targets
        self._field_types = field_types
        self._max_concurrency = max_concurrency
        self._max_budget_usd = max_budget_usd

        # 2. Build the steps; the engine topo-orders them by their input bindings.
        self._steps = [
            IngestStageMetagenStepBudgetGate(targets, field_types, max_budget_usd),
            IngestStageMetagenStepChunkScope(targets, field_types, max_concurrency),
            IngestStageMetagenStepDocScope(targets, field_types),
            IngestStageMetagenStepAssembleDocMeta(),
        ]

    @property
    def children(self) -> list:
        """The metagen steps (budget_gate -> chunk_scope / doc_scope -> assemble_doc_meta)."""
        return self._steps

    def aggregate(self, child_outputs: dict[str, NodeOutput]) -> IngestStageMetagenOutput:
        """
        Combine the step outputs into the stage output.

        Args:
            child_outputs (dict[str, NodeOutput]): Step key -> its output.

        Returns:
            IngestStageMetagenOutput: The assembled metagen result (chunks + doc_fields + doc_meta +
                metagen_result), taken from the assemble step which closes the IO graph.
        """
        # 1. The assemble step holds every downstream-facing field (chunks/doc_fields/doc_meta/result).
        assembled = child_outputs["assemble_doc_meta"]

        # 2. Re-expose them as the stage's single output artefact.
        return IngestStageMetagenOutput(
            chunks=assembled.chunks,
            doc_fields=assembled.doc_fields,
            doc_meta=assembled.doc_meta,
            metagen_result=assembled.metagen_result,
        )


__all__ = ["IngestStageMetagen"]
