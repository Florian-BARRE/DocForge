# ====== Code Summary ======
# StageResolver — resolves the effective S0–S6 stage stack for a single engine run.
# With no per-run PipelineConfig (or no registry) the injected default stages are used; with
# a config + registry the parser/S2/S4/S5 stages are rebuilt from that config and a per-run
# S6 is built from the collection's embed config.  Extracted from StageEngine.core so the
# engine stays a thin orchestrator.

# ====== Standard Library Imports ======
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from common_libs.pipeline.assembly import ProviderRegistry
    from common_libs.pipeline.stages.s1_parse.core import S1ParseStage as _S1ParseStageType

# ====== Internal Project Imports ======
from common_libs.config.pipeline import PipelineConfig
from common_libs.storage.qdrant.client import QdrantStorageClient
from common_libs.pipeline.stages.s0_ingest.core import S0IngestStage
from common_libs.pipeline.stages.s1_parse.core import S1ParseStage
from common_libs.pipeline.stages.s2_enrich import S2EnrichStage
from common_libs.pipeline.stages.s4_chunk import S4ChunkStage
from common_libs.pipeline.stages.s5_contextualize.core import S5ContextualizeStage
from common_libs.pipeline.stages.s6_embed_index.core import S6EmbedIndexStage

# ====== Local Project Imports ======
from .deps import StageDeps
from .s6_builder import S6Builder

# Type alias for the resolved 6-stage tuple.
ResolvedStageTuple = tuple[
    S0IngestStage,
    "_S1ParseStageType",
    S2EnrichStage,
    S4ChunkStage,
    S5ContextualizeStage,
    S6EmbedIndexStage | None,
]


class StageResolver:
    """
    Static resolver for the per-run S0–S6 stage stack.

    Operates on the engine's injected default stages plus its registry/qdrant; returns the
    six stages to execute for a given (optional) per-run PipelineConfig.
    """

    def __new__(cls, *args: object, **kwargs: object) -> None:  # type: ignore[misc]
        """Block instantiation — this is a static-only helper class."""
        raise TypeError("StageResolver is a static-only class and cannot be instantiated.")

    @staticmethod
    def resolve(
        pipeline_config: PipelineConfig | None,
        deps: StageDeps,
        registry: ProviderRegistry | None,
        qdrant: QdrantStorageClient | None,
        defaults: ResolvedStageTuple,
    ) -> ResolvedStageTuple:
        """
        Resolve the effective stage stack for a run.

        With no per-run config (or no registry), the injected default stages are used —
        preserving the env-configured behavior of the worker and FastAPI app.  With a
        config and a registry, the parser and S2/S4/S5 stages are rebuilt from that config,
        making the pipeline parameterizable per-run.  S6 is rebuilt per-run from the
        collection's embed config (it owns the live Qdrant connection).

        Args:
            pipeline_config (PipelineConfig | None): The per-run configuration, or None.
            deps (StageDeps): Shared infra container (S3 + chunk_repo used here).
            registry (ProviderRegistry | None): Resolves config → stages, or None.
            qdrant (QdrantStorageClient | None): Live Qdrant client for per-run S6 builds.
            defaults (ResolvedStageTuple): The engine's injected default (s0..s6) stack.

        Returns:
            ResolvedStageTuple: (s0, s1, s2, s4, s5, s6) — the stages to execute this run.

        Raises:
            ProviderUnavailableError: When the config requests an unavailable provider.
        """
        # 1. No config or no registry → injected defaults (env-configured behavior)
        if pipeline_config is None or registry is None:
            return defaults

        s0_default, _s1_default, _s2, _s4, _s5, _s6 = defaults

        # 2. Resolve parse chain + S2/S4/S5 from config; wrap parse chain into S1
        resolved = registry.build_stages(pipeline_config)
        s1 = S1ParseStage(parse_chain=resolved.parse_chain, s3=deps.s3)

        # 3. Build a per-run S6 from the collection's embed config (overrides injected default)
        s6 = S6Builder.build(pipeline_config.embed, qdrant, deps.chunk_repo, registry)
        return s0_default, s1, resolved.s2, resolved.s4, resolved.s5, s6


# ------------------- Public API ------------------- #
__all__ = ["StageResolver", "ResolvedStageTuple"]
