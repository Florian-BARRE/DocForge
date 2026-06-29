# ====== Code Summary ======
# SplitterBuilder — turns the chunk stage's chosen split_method config variant (a discriminated
# union: token_budget / sentence_window / semantic) into the matching intra-section SectionSplitter
# instance injected into the chunk stage. The semantic splitter needs an embedder for boundary
# detection, so it borrows the first provider of the already-built embed chain; the other two are
# pure. Kept separate from ChainBuilder because a splitter is a single strategy object, not an
# escalation chain.

# ====== Standard Library Imports ======
from typing import Any

# ====== Third-Party Library Imports ======
from loggerplusplus import loggerplusplus

# ====== Internal Project Imports ======
from common_libs.pipelines.capabilities.chain import Chain
from common_libs.pipelines.core.ingest.stages.chunk.steps.chunk.chunker.strategies.base import (
    SectionSplitter,
)
from common_libs.pipelines.core.ingest.stages.chunk.steps.chunk.chunker.strategies.semantic import (
    SemanticSplitter,
)
from common_libs.pipelines.core.ingest.stages.chunk.steps.chunk.chunker.strategies.sentence_window import (
    SentenceWindowSplitter,
)
from common_libs.pipelines.core.ingest.stages.chunk.steps.chunk.chunker.strategies.token_budget import (
    TokenBudgetSplitter,
)

# ====== Local Project Imports ======
from .errors import PipelineBuildError


class SplitterBuilder:
    """Static builder mapping a chunk ``split_method`` config to a live SectionSplitter."""

    logger = loggerplusplus.bind(identifier="SplitterBuilder")

    def __new__(cls, *args: object, **kwargs: object) -> None:
        raise TypeError("SplitterBuilder is a static-only class and cannot be instantiated.")

    @classmethod
    def build(cls, split_method: Any, embed_chain: Chain | None = None) -> SectionSplitter:
        """
        Build the intra-section splitter selected by a chunk ``split_method`` config.

        Args:
            split_method (Any): A split-method config variant (discriminated on ``id``:
                ``token_budget`` / ``sentence_window`` / ``semantic``).
            embed_chain (Chain | None): The built embed chain — only the ``semantic`` method uses it
                (its first provider supplies boundary embeddings).

        Returns:
            SectionSplitter: The wired splitter to inject into the chunk stage.

        Raises:
            PipelineBuildError: On an unknown method id, or a semantic method with no embed provider.
        """
        # 1. Dispatch on the discriminator; map each variant's pure params to its splitter.
        method_id = getattr(split_method, "id", None)
        if method_id == "token_budget":
            return TokenBudgetSplitter(
                max_tokens=split_method.max_tokens,
                overlap_blocks=split_method.overlap_blocks,
            )
        if method_id == "sentence_window":
            return SentenceWindowSplitter(
                window_sentences=split_method.window_sentences,
                stride_sentences=split_method.stride_sentences,
                max_tokens=split_method.max_tokens,
            )
        if method_id == "semantic":
            # 2. Semantic boundaries need an embedder — borrow the embed chain's first provider.
            if embed_chain is None or not embed_chain.providers:
                raise PipelineBuildError(
                    "The 'semantic' split_method requires a non-empty embed chain for boundary "
                    "detection, but none was configured."
                )
            return SemanticSplitter(
                embed_provider=embed_chain.providers[0],
                max_tokens=split_method.max_tokens,
                min_tokens=split_method.min_tokens,
                breakpoint_percentile=split_method.breakpoint_percentile,
            )
        raise PipelineBuildError(f"Unknown chunk split_method id: {method_id!r}.")


__all__ = ["SplitterBuilder"]
