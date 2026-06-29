# ====== Code Summary ======
# IngestStageEmbedIndexEmbedHelpers — the embed-side static helpers shared by the embed_content and
# embed_fields steps. Runs the embed chain in batches with the load-bearing POSITIONAL CONTRACT
# (degraded batches emit same-length None placeholders so vectors stay 1:1 with their chunks), and
# converts each chain outcome into a domain ChainTrace for lineage. Pure over an injected chain.

# ====== Third-Party Library Imports ======
from loggerplusplus import loggerplusplus

# ====== Internal Project Imports ======
from common_libs.domain.ir.models import ChainAttemptIR, ChainTrace
from common_libs.pipelines.capabilities.chain import (
    Chain,
    ChainHelpers,
    ChainOutcome,
    chain_outcome_to_attempt_dicts,
)


class IngestStageEmbedIndexEmbedHelpers:
    """
    Static helpers driving the embed chain in batches for the embed_index stage.

    Groups the batched ``embed_texts`` (positional-aligned dense/sparse vectors + per-batch traces)
    and ``embed_values`` (scatter only non-empty field values back per chunk). No instance state.
    """

    logger = loggerplusplus.bind(identifier="IngestStageEmbedIndexEmbedHelpers")

    def __new__(cls, *args: object, **kwargs: object) -> None:
        """Block instantiation — this is a static-only helper class."""
        raise TypeError(
            "IngestStageEmbedIndexEmbedHelpers is a static-only class and cannot be instantiated."
        )

    @classmethod
    async def embed_texts(
        cls,
        chain: Chain,
        texts: list[str],
        batch_size: int,
    ) -> tuple[list[list[float] | None], list[dict[int, float] | None] | None, list[ChainTrace]]:
        """
        Embed a list of texts via the embed chain, batched per ``batch_size``.

        POSITIONAL CONTRACT: the returned lists are aligned 1:1 with ``texts`` — ``all_dense[i]`` is
        the vector for ``texts[i]`` (or ``None`` when its batch degraded). This is load-bearing: the
        downstream upsert aligns chunks to vectors by index, so a degraded batch MUST contribute
        same-length ``None`` placeholders rather than be dropped (dropping would shift every later
        chunk onto the wrong vector).

        Args:
            chain (Chain): The ordered embed chain (a service injected into the step).
            texts (list[str]): Texts to embed (may be empty).
            batch_size (int): Texts sent per chain attempt.

        Returns:
            tuple: ``(all_dense, all_sparse_or_None, traces)`` — ``all_dense`` / ``all_sparse`` are
                aligned 1:1 with ``texts`` (``None`` where the chain degraded); ``all_sparse`` is
                ``None`` only when NO batch produced sparse vectors; ``traces`` is one per batch.

        Raises:
            ChainExhaustedError: When the chain exhausts every provider for a batch under the embed
                gate's ``failure_policy="raise"`` (the default); the worker boundary then fails the doc.
        """
        all_dense: list[list[float] | None] = []
        all_sparse: list[dict[int, float] | None] | None = None
        traces: list[ChainTrace] = []
        for i in range(0, len(texts), batch_size):
            batch = texts[i : i + batch_size]
            # The chain applies its own failure policy on exhaustion: raise -> ChainExhaustedError
            # propagates (doc failed); continue -> degraded outcome (result=None) -> emit same-length
            # None placeholders to preserve alignment.
            outcome = await chain.call(lambda p: p.embed(batch))
            traces.append(cls._build_trace(outcome))
            if outcome.result is None:
                # Reached only under failure_policy="continue": placeholder this batch so its chunks
                # index with no content vector rather than shifting every subsequent chunk.
                cls.logger.warning(
                    f"Embed chain degraded for batch of {len(batch)} texts — emitting "
                    f"{len(batch)} None placeholder(s) per failure_policy=continue."
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
        return all_dense, all_sparse, traces

    @classmethod
    async def embed_values(
        cls,
        chain: Chain,
        values: list[str | None],
        batch_size: int,
    ) -> tuple[list[list[float] | None], list[dict[int, float] | None], list[ChainTrace]]:
        """
        Embed only the non-empty field values, scattering results back per chunk.

        Chunks with no value for the field get ``None`` (no named vector on that point). A degraded
        embed batch also yields ``None`` for its values, so the positional scatter stays correct and
        never raises ``IndexError``.

        Args:
            chain (Chain): The ordered embed chain.
            values (list[str | None]): Per-chunk field values (None / empty = skip).
            batch_size (int): Texts sent per chain attempt.

        Returns:
            tuple: ``(dense_out, sparse_out, traces)`` aligned to ``values`` (None where skipped or
                where the embed chain degraded); ``traces`` is one per batch actually embedded.
        """
        dense_out: list[list[float] | None] = [None] * len(values)
        sparse_out: list[dict[int, float] | None] = [None] * len(values)
        idxs = [i for i, v in enumerate(values) if v]
        if not idxs:
            return dense_out, sparse_out, []
        dense, sparse, traces = await cls.embed_texts(
            chain, [values[i] or "" for i in idxs], batch_size
        )
        for j, i in enumerate(idxs):
            dense_out[i] = dense[j]
            if sparse is not None:
                sparse_out[i] = sparse[j]
        return dense_out, sparse_out, traces

    @staticmethod
    def _build_trace(outcome: ChainOutcome) -> ChainTrace:
        """
        Convert a chain outcome into the domain ChainTrace stamped on the IR.

        Args:
            outcome (ChainOutcome): The per-batch chain invocation record.

        Returns:
            ChainTrace: Stage-labelled ``"embed"`` trace carrying every attempt + degraded flag.
        """
        return ChainTrace(
            stage="embed",
            attempts=[ChainAttemptIR(**d) for d in chain_outcome_to_attempt_dicts(outcome)],
            final_provider=outcome.final_provider,
            degraded=outcome.degraded,
            gate_tripped=ChainHelpers.gate_tripped(outcome) if outcome.degraded else None,
        )


__all__ = ["IngestStageEmbedIndexEmbedHelpers"]
