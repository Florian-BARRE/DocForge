# ====== Code Summary ======
# ChunkStageAssembler — builds the S4 chunking stage from a typed ChunkConfig: it resolves
# the intra-section split method (probing reachability for the semantic method) and wires the
# heading skeleton + atomic policy + mode around it.  Extracted from ProviderRegistry so the
# resolution core stays small; depends only on RUNTIME_CONFIG (no S3 / provider cache).

# ====== Standard Library Imports ======
from __future__ import annotations

from typing import Any

# ====== Internal Project Imports ======
from common_libs.config.pipeline import ChunkConfig, SplitMethodConfig
from common_libs.pipeline.stages.s4_chunk import SectionSplitter, SemanticConfig as SemanticParams
from common_libs.pipeline.stages.s4_chunk import S4ChunkStage

# ====== Local Project Imports ======
from .availability import AvailabilityProbes, ProviderUnavailableError


class ChunkStageAssembler:
    """
    Static builder for the S4 chunking stage and its intra-section splitter.

    All methods take the RUNTIME_CONFIG instance (``cfg``) so deployment defaults (e.g.
    the bge_server host for semantic chunking) can be merged into the typed config.
    """

    def __new__(cls, *args: object, **kwargs: object) -> None:  # type: ignore[misc]
        """Block instantiation — this is a static-only helper class."""
        raise TypeError("ChunkStageAssembler is a static-only class and cannot be instantiated.")

    @classmethod
    def build_chunk_stage(cls, cfg: Any, chunk: ChunkConfig) -> S4ChunkStage:
        """
        Build the S4 chunking stage from config: split method + atomic policy + mode.

        Args:
            cfg (Any): RUNTIME_CONFIG — deployment defaults merged into the split config.
            chunk (ChunkConfig): The chunking configuration block.

        Returns:
            S4ChunkStage: Wired chunking stage.

        Raises:
            ProviderUnavailableError: When the semantic method is requested but TEI is unreachable.
        """
        # 1. Resolve the intra-section split method (the decision-tree-by-method)
        splitter = cls.build_splitter(cfg, chunk.split_method)

        # 2. Wire the heading skeleton + atomic policy + mode around it
        return S4ChunkStage(
            splitter=splitter,
            heading_rules=chunk.heading_rules,
            reinject_breadcrumb=chunk.reinject_breadcrumb,
            merge_short_sections=chunk.merge_short_sections,
            atomic=chunk.atomic,
            cross_references=chunk.cross_references,
            hierarchical=chunk.hierarchical,
        )

    @staticmethod
    def build_splitter(cfg: Any, spec: SplitMethodConfig) -> SectionSplitter:
        """
        Instantiate the requested intra-section split method from its typed config.

        Merges deployment defaults into the typed config then delegates to build().
        Semantic split requires a reachable embed endpoint and is checked before build().

        Args:
            cfg (Any): RUNTIME_CONFIG — deployment defaults merged into the split config.
            spec (SplitMethodConfig): Typed split method config (discriminated union).

        Returns:
            SectionSplitter: Wired splitter.

        Raises:
            ProviderUnavailableError: When semantic is requested but the embed endpoint is unreachable.
        """
        # 1. Merge deployment defaults into the typed config (the bge_server host for semantic)
        merged = spec.merge_defaults(cfg)

        # 2. Semantic split now accepts any embed provider — only a LOCAL base_url is probed
        # for reachability; cloud HTTPS endpoints are assumed reachable and will report an
        # actionable error at the first ``embed()`` call if they aren't.
        if isinstance(merged, SemanticParams):
            embed_cfg = getattr(merged, "embed", None)
            embed_url = getattr(embed_cfg, "base_url", "") or "" if embed_cfg else ""
            if embed_url and not embed_url.startswith("https://"):
                if not AvailabilityProbes.endpoint_reachable(embed_url):
                    raise ProviderUnavailableError(
                        "split_method", "semantic",
                        f"Semantic chunking needs a reachable embed endpoint (got {embed_url!r}).",
                    )

        # 3. Delegate instantiation to the typed config (build() knows its own splitter)
        return merged.build()


# ------------------- Public API ------------------- #
__all__ = ["ChunkStageAssembler"]
