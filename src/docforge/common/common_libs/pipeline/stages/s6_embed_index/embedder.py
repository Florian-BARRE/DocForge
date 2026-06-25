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

from common_libs.providers.chain import Chain, ChainHelpers, chain_outcome_to_attempt_dicts

# ====== Internal Project Imports ======
from common_libs.domain.ir.models import ChainAttemptIR, ChainTrace


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
    ) -> tuple[list[list[float] | None], list[dict[int, float] | None] | None]:
        """
        Embed a list of texts via the embed chain, batched per ``embed_batch_size``.

        Each batch contributes one ``ChainTrace`` to ``self.batch_traces``; the engine
        flushes them onto the document IR after the stage returns.

        POSITIONAL CONTRACT: the returned lists are aligned 1:1 with ``texts`` —
        ``all_dense[i]`` is the vector for ``texts[i]`` (or ``None`` when its batch
        degraded). This is load-bearing: downstream upsert aligns chunks to vectors by
        index, so a degraded batch MUST contribute same-length ``None`` placeholders,
        never be dropped (dropping would shift every later chunk onto the wrong vector).

        Args:
            texts (list[str]): Texts to embed.

        Returns:
            tuple: ``(all_dense, all_sparse_or_None)`` — both aligned 1:1 with ``texts``.
                Entries are ``None`` where the chain degraded (continue) for that batch;
                ``all_sparse`` is ``None`` only when NO batch produced sparse vectors at all.

        Raises:
            ChainExhaustedError: When the chain exhausts every provider for a batch AND the
                embed gate's ``failure_policy="raise"`` (the default). The chain raises with a
                precise per-provider reason; the worker fail-closed boundary marks the doc
                ``failed``. A collection that sets ``failure_policy="continue"`` instead
                yields a degraded (result=None) outcome — that batch contributes None placeholders.
        """
        all_dense: list[list[float] | None] = []
        all_sparse: list[dict[int, float] | None] | None = None
        for i in range(0, len(texts), self._embed_batch_size):
            batch = texts[i : i + self._embed_batch_size]
            # The chain applies its own failure policy on exhaustion: raise →
            # ChainExhaustedError propagates (doc failed); continue → degraded outcome
            # (result=None) → emit same-length None placeholders to preserve alignment.
            outcome = await self._embed_chain.call(lambda p: p.embed(batch))
            self.batch_traces.append(ChainTrace(
                stage="embed",
                attempts=[ChainAttemptIR(**d) for d in chain_outcome_to_attempt_dicts(outcome)],
                final_provider=outcome.final_provider,
                degraded=outcome.degraded,
                gate_tripped=ChainHelpers.gate_tripped(outcome) if outcome.degraded else None,
            ))
            if outcome.result is None:
                # Reached only under failure_policy="continue": placeholder this batch so its
                # chunks index with no content vector (skipped by _build_point) rather than
                # shifting every subsequent chunk onto the wrong vector.
                self.logger.warning(
                    f"S6 embed chain degraded for batch of {len(batch)} texts — "
                    f"emitting {len(batch)} None placeholder(s) per failure_policy=continue."
                )
                all_dense.extend([None] * len(batch))
                if all_sparse is not None:
                    all_sparse.extend([None] * len(batch))
                continue
            res = outcome.result
            all_dense.extend(res.vectors)
            if res.sparse is not None:
                # First sparse-producing batch: back-fill None for any earlier (dense-only or
                # degraded) batches so the sparse list stays index-aligned with all_dense.
                if all_sparse is None:
                    all_sparse = [None] * (len(all_dense) - len(res.sparse))
                all_sparse.extend(res.sparse)
            elif all_sparse is not None:
                # A dense-only success after sparse appeared: placeholder to keep alignment.
                all_sparse.extend([None] * len(res.vectors))
        return all_dense, all_sparse

    async def embed_values(
        self, values: list[str | None]
    ) -> tuple[list[list[float] | None], list[dict[int, float] | None]]:
        """
        Embed only the non-empty field values, scattering results back per chunk.

        Chunks with no value for the field get None (→ no named vector on that point).
        A degraded embed batch (failure_policy=continue) also yields None for its values —
        ``embed_texts`` returns same-length None placeholders, so ``dense[j]`` may be None;
        the positional scatter below stays correct and never raises IndexError.

        Args:
            values (list[str | None]): Per-chunk field values (None / empty = skip).

        Returns:
            tuple: ``(dense_out, sparse_out)`` aligned to ``values`` (None where skipped
                or where the embed chain degraded).
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
