# ====== Code Summary ======
# S6Embedder — runs the S6 embed chain in batches and scatters field-value embeddings back
# onto their chunks.  Owns the embed chain, the batch size, and the per-run ChainTrace
# accumulator.  Extracted from S6EmbedIndexStage so the stage focuses on vector-plan
# assembly + Qdrant/Postgres I/O.

# ====== Standard Library Imports ======
from __future__ import annotations

from typing import Any

# ====== Third-Party Library Imports ======
from loggerplusplus import LoggerClass

from libs.providers.chain import Chain, chain_outcome_to_attempt_dicts

# ====== Internal Project Imports ======
from libs.domain.ir.models import ChainAttemptIR, ChainTrace


class S6Embedder(LoggerClass):
    """
    Batches text through the S6 embed chain and records one ChainTrace per batch.

    Holds the embed chain, the batch size, and the run-scoped ``batch_traces`` accumulator
    (reset by ``begin_run`` before each stage execution).  The owning stage flushes the
    accumulated traces onto the document IR after the stage returns.
    """

    def __init__(self, embed_chain: Chain[Any, Any], embed_batch_size: int = 64) -> None:
        """
        Initialize the embedder.

        Args:
            embed_chain (Chain[EmbedProvider, EmbedResult]): Ordered embed chain.
                Index 0 is tried first; the gate escalates when a provider raises.
            embed_batch_size (int): Texts sent per chain attempt.
        """
        LoggerClass.__init__(self)
        self._embed_chain = embed_chain
        self._embed_batch_size = embed_batch_size
        self.batch_traces: list[ChainTrace] = []

    @property
    def embed_chain(self) -> Chain[Any, Any]:
        """Expose the chain so the engine can fingerprint its signature."""
        return self._embed_chain

    @property
    def dimension(self) -> int:
        """Return the dimension of the first embed provider (used by ensure_collection)."""
        first = self._embed_chain.providers[0] if self._embed_chain.providers else None
        return int(getattr(first, "dimension", 0))

    def begin_run(self) -> None:
        """Reset the per-run trace accumulator before a new stage execution."""
        self.batch_traces = []

    async def embed_texts(
        self, texts: list[str]
    ) -> tuple[list[list[float]], list[dict[int, float]] | None]:
        """
        Embed a list of texts via the embed chain, batched per ``embed_batch_size``.

        Each batch contributes one ``ChainTrace`` to ``self.batch_traces``; the engine
        flushes them onto the document IR after the stage returns.

        Args:
            texts (list[str]): Texts to embed.

        Returns:
            tuple: ``(all_dense, all_sparse_or_None)``.

        Raises:
            RuntimeError: When the chain exhausts every provider for a batch.
        """
        all_dense: list[list[float]] = []
        all_sparse: list[dict[int, float]] | None = None
        for i in range(0, len(texts), self._embed_batch_size):
            batch = texts[i : i + self._embed_batch_size]
            outcome = await self._embed_chain.call(lambda p: p.embed(batch))
            self.batch_traces.append(ChainTrace(
                stage="embed",
                attempts=[ChainAttemptIR(**d) for d in chain_outcome_to_attempt_dicts(outcome)],
                final_provider=outcome.final_provider,
            ))
            if outcome.result is None:
                raise RuntimeError(
                    f"S6 embed chain exhausted for batch of {len(batch)} texts — "
                    f"{len(outcome.attempts)} provider(s) attempted, none returned vectors."
                )
            res = outcome.result
            all_dense.extend(res.vectors)
            if res.sparse is not None:
                if all_sparse is None:
                    all_sparse = []
                all_sparse.extend(res.sparse)
        return all_dense, all_sparse

    async def embed_values(
        self, values: list[str | None]
    ) -> tuple[list[list[float] | None], list[dict[int, float] | None]]:
        """
        Embed only the non-empty field values, scattering results back per chunk.

        Chunks with no value for the field get None (→ no named vector on that point).

        Args:
            values (list[str | None]): Per-chunk field values (None / empty = skip).

        Returns:
            tuple: ``(dense_out, sparse_out)`` aligned to ``values`` (None where skipped).
        """
        dense_out: list[list[float] | None] = [None] * len(values)
        sparse_out: list[dict[int, float] | None] = [None] * len(values)
        idxs = [i for i, v in enumerate(values) if v]
        if not idxs:
            return dense_out, sparse_out
        dense, sparse = await self.embed_texts([values[i] or "" for i in idxs])
        for j, i in enumerate(idxs):
            dense_out[i] = dense[j]
            if sparse is not None:
                sparse_out[i] = sparse[j]
        return dense_out, sparse_out


# ------------------- Public API ------------------- #
__all__ = ["S6Embedder"]
