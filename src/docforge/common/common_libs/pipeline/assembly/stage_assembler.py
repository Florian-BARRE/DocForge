# ====== Code Summary ======
# build_pipeline — assembles the ingestion stage list from a PipelineConfig. It (a) topo-sorts the
# registered native stages by their AFTER edges, (b) validates the CONSUMES/PRODUCES IO graph, then
# (c) instantiates each stage's INNER implementation via the shared ProviderRegistry inner builders
# (_build_parser_chain / _build_s2 / _build_metagen / _build_embed_chain + ChunkStageAssembler) and
# wraps it in the matching native stage. This is the SOLE ingestion assembler (the legacy
# StageResolver / StageEngine were removed in PR-5; the adapter shims were removed once every stage
# became native).
#
# The S6 build sequence (registry-built embed chain → S6 stage, None when infra absent) is replicated
# here in-layer because common_libs may not import the worker (layer DAG).

# ====== Standard Library Imports ======
from __future__ import annotations

from typing import TYPE_CHECKING, Any

# ====== Internal Project Imports ======
# Importing the ingest stages package is the registration backstop: it forces every stage's
# @register_stage to fire even if auto_import_stages() has not yet been called. All ingest stages
# are now native under ingest.stages. The concrete classes are looked up from the registry
# (get_stages), never referenced by name here.
from common_libs.pipeline.ingest import stages as _ingest_stages  # noqa: F401 — force @register_stage
from common_libs.pipeline.base.stage.core import AbstractStage
from common_libs.pipeline.stages.s0_ingest.core import S0IngestStage
from common_libs.pipeline.stages.s1_parse.core import S1ParseStage
from common_libs.pipeline.stages.s5_contextualize.core import S5ContextualizeStage
from common_libs.pipeline.stages.s6_embed_index.core import S6EmbedIndexStage
from common_libs.pipeline.bricks.providers.converter import GotenbergConverter

# ====== Local Project Imports ======
from .chunk_stage_assembler import ChunkStageAssembler
from .stage_registry import (
    StageWiringError,
    auto_import_stages,
    get_stages,
    topo_order,
    validate_wiring,
)

if TYPE_CHECKING:
    from common_libs.config.pipeline import EmbedConfig, PipelineConfig
    from common_libs.pipeline.stages.context import StageDeps
    from common_libs.storage.qdrant.client import QdrantStorageClient
    from .registry import ProviderRegistry


class PipelineAssembler:
    """
    Static assembler that turns a PipelineConfig into the ordered native stage list.

    Each stage's inner implementation is built by the exact same builder the legacy path uses; the
    native stage wraps it unchanged so byte-for-byte parity holds. No instance state.
    """

    def __new__(cls, *args: object, **kwargs: object) -> None:  # type: ignore[misc]
        """Block instantiation — this is a static-only assembler."""
        raise TypeError("PipelineAssembler is a static-only class and cannot be instantiated.")

    @classmethod
    def build_pipeline(
        cls,
        config: PipelineConfig,
        provider_registry: ProviderRegistry,
        deps: StageDeps,
        qdrant: QdrantStorageClient | None,
        metadata_fields: list[Any] | None = None,
    ) -> list[AbstractStage]:
        """
        Assemble the ordered, IO-validated list of native stages for a run.

        Args:
            config (PipelineConfig): The per-run pipeline configuration.
            provider_registry (ProviderRegistry): Builds the inner chains (availability-checked).
            deps (StageDeps): Shared infra handles (S3, Postgres, chunk_repo, …).
            qdrant (QdrantStorageClient | None): Live Qdrant client for the embed/index stage.
            metadata_fields (list | None): The collection's metadata field specs (feeds metagen).

        Returns:
            list[AbstractStage]: Native stages in topological order. The embed/index stage
                is omitted when its infrastructure (Qdrant / chunk_repo) is unavailable — mirroring
                the legacy ``S6 = None`` "persist-only, no indexing" path.

        Raises:
            StageWiringError: On a cycle, an unknown AFTER dependency, or a broken IO graph.
        """
        # 1. Discover + order + validate the registered stage graph.
        auto_import_stages()
        ordered = topo_order(list(get_stages().values()))
        validate_wiring(ordered)

        # 2. Build each stage's inner implementation and wrap it in its native stage (skip a None S6).
        stages: list[AbstractStage] = []
        for stage_cls in ordered:
            inner = cls._build_inner(stage_cls.KEY, config, provider_registry, deps, qdrant, metadata_fields)
            if stage_cls.KEY == "embed_index" and inner is None:
                continue
            stages.append(stage_cls(inner))
        return stages

    @classmethod
    def _build_inner(
        cls,
        key: str,
        config: PipelineConfig,
        registry: ProviderRegistry,
        deps: StageDeps,
        qdrant: QdrantStorageClient | None,
        metadata_fields: list[Any] | None,
    ) -> Any:
        """
        Build the inner legacy stage for ``key`` via the exact builder the legacy path uses.

        Args:
            key (str): The stage KEY (registry/adapter identity).
            config (PipelineConfig): The per-run config (flat reads: ``config.parse`` etc.).
            registry (ProviderRegistry): Builds chains + S2/S5b; holds RUNTIME_CONFIG for S0/S4.
            deps (StageDeps): Shared infra handles.
            qdrant (QdrantStorageClient | None): Live Qdrant client (embed/index only).
            metadata_fields (list | None): Collection metadata field specs (metagen only).

        Returns:
            Any: The inner legacy stage instance (or None for embed/index when infra is absent).

        Raises:
            StageWiringError: When ``key`` has no known inner builder.
        """
        if key == "ingest":
            # S0 is constant (not config-driven); its converter comes from RUNTIME_CONFIG (held by
            # the registry as ._cfg, mirroring how S012ParamHelpers reaches the converter today).
            rc = registry._cfg
            converter = GotenbergConverter(base_url=rc.GOTENBERG_URL, timeout_s=rc.GOTENBERG_TIMEOUT_S)
            return S0IngestStage(s3=deps.s3, converter=converter)
        if key == "parse":
            chain = registry._build_parser_chain(config.parse.chain, config.parse.gate)
            return S1ParseStage(parse_chain=chain, s3=deps.s3)
        if key == "enrich":
            return registry._build_s2(config.enrich)
        if key == "chunk":
            return ChunkStageAssembler.build_chunk_stage(registry._cfg, config.chunk)
        if key == "contextualize":
            return S5ContextualizeStage(config=config.contextualize)
        if key == "metagen":
            return registry._build_metagen(config.metagen, metadata_fields)
        if key == "embed_index":
            return cls._build_s6(config.embed, qdrant, deps.chunk_repo, registry)
        raise StageWiringError(f"No inner-stage builder registered for stage KEY {key!r}.")

    @staticmethod
    def _build_s6(
        embed: EmbedConfig,
        qdrant: QdrantStorageClient | None,
        chunk_repo: Any,
        registry: ProviderRegistry,
    ) -> S6EmbedIndexStage | None:
        """
        Replicate the worker's S6Builder.build sequence in-layer (common may not import worker).

        Args:
            embed (EmbedConfig): Collection embed config (typed provider spec).
            qdrant (QdrantStorageClient | None): Live Qdrant client.
            chunk_repo (Any): Chunk repository (None when unavailable).
            registry (ProviderRegistry): Builds the embed chain (availability-checked).

        Returns:
            S6EmbedIndexStage | None: The S6 stage, or None when Qdrant/chunk_repo are absent.
        """
        # 1. Guard: infrastructure must be present to build S6 (else no indexing — same as legacy).
        if qdrant is None or chunk_repo is None:
            return None

        # 2. Build the embed chain via the registry (gate + availability + sparse backend).
        embed_chain = registry._build_embed_chain(embed.chain, embed.gate, getattr(embed, "sparse", None))
        if embed_chain is None:
            return None

        # 3. Construct the S6 stage (batch size from the first spec, default 32 — verbatim S6Builder).
        first_spec = embed.chain[0] if embed.chain else None
        batch_size = getattr(first_spec, "batch_size", 32)
        return S6EmbedIndexStage(
            embed_chain=embed_chain,
            qdrant=qdrant,
            chunk_repo=chunk_repo,
            embed_batch_size=batch_size,
        )


def build_pipeline(
    config: PipelineConfig,
    provider_registry: ProviderRegistry,
    deps: StageDeps,
    qdrant: QdrantStorageClient | None,
    metadata_fields: list[Any] | None = None,
) -> list[AbstractStage]:
    """Module-level wrapper — assemble the ordered adapter-wrapped stage list (see PipelineAssembler)."""
    return PipelineAssembler.build_pipeline(config, provider_registry, deps, qdrant, metadata_fields)


__all__ = ["PipelineAssembler", "build_pipeline"]
