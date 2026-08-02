# ====== Code Summary ======
# BaseEmbedderNode — the abstract base of every embedder. The shared frame: keep only the chunks
# whose role is enabled by default (role_default_enabled is THE single policy: body embeds,
# furniture like header/footer & toc does not — no vector spend on unsearchable chunks), batch
# their ENRICHED texts through the provider hooks (dense required, sparse optional), embed the
# SEMANTIC chunk-field values as named per-field vectors, and assemble the chunk-linked output.
# Disabled chunks simply get NO vectors (they still flow to persistence via the chunk artefact,
# inspectable + re-enablable). Embedding an enabled chunk is NOT optional: any provider failure
# fails the node — no degradation here.

# ====== Standard Library Imports ======
import asyncio
import re
from abc import abstractmethod
from collections.abc import Awaitable, Callable
from typing import TypeVar

# ====== Third-Party Library Imports ======
import httpx

# ====== Internal Project Imports ======
from shared_libs.pipelines.base import ActionNode
from shared_libs.public_models import (
    Chunk,
    ChunkEmbeddings,
    ChunkVectors,
    CollectionContract,
    FieldScope,
    SparseVector,
    role_default_enabled,
)

# ====== Local Project Imports ======
from .config import BaseEmbedConfig
from .io import EmbedConsumes, EmbedProduces

# A bare figure marker line — an "[Image: <kind>]" with NOTHING after the closing bracket (no
# caption/OCR/description folded onto it). Such a line carries no searchable content of its own.
_BARE_IMAGE_MARKER = re.compile(r"^\[Image:[^\]]*\]$")

# The shape a resilient wrapper carries through its retry/split skeleton (a dense list, or the
# (dense, sparse) pair of the combined path). Bound so the skeleton stays provider-agnostic.
_Batch = TypeVar("_Batch")


class BaseEmbedderNode(ActionNode):
    """Abstract embedder: chunks in, chunk-linked vectors out; children implement the hooks."""

    Consumes = EmbedConsumes
    Produces = EmbedProduces

    @staticmethod
    def _has_searchable_content(text: str) -> bool:
        """Whether a chunk's enriched text carries anything worth embedding.

        A chunk whose text is ONLY whitespace and/or bare ``[Image: <kind>]`` figure markers (a
        cropped-but-unenriched figure with no caption/OCR/description) has no real content: embedding
        it spends a vector on a placeholder that then surfaces as a top hit with a misleading
        self-citation (the empty chunk still names a real filename). Conservative on purpose — a line
        that is a marker WITH text folded in ("[Image: chart] Figure 2 …"), or any other non-blank
        line, counts as content and keeps the chunk embedded.
        """
        for line in text.splitlines():
            stripped = line.strip()
            if stripped and not _BARE_IMAGE_MARKER.match(stripped):
                return True
        return False

    @abstractmethod
    async def _embed_dense(self, texts: list[str]) -> list[list[float]]:
        """Embed one batch of texts into dense vectors (same order)."""
        ...

    async def _embed_sparse(self, texts: list[str]) -> list[SparseVector] | None:
        """Embed one batch into sparse vectors — None when the provider has none (default)."""
        _ = texts
        return None

    async def _embed_dense_sparse(
        self, texts: list[str]
    ) -> tuple[list[list[float]], list[SparseVector]] | None:
        """Embed one batch into dense AND sparse vectors in a single forward pass.

        Optional optimisation: a provider that can emit both axes from one model pass (a combined
        endpoint) overrides this to halve the embed cost versus two separate round-trips. Returning
        None — the default — means "this provider has no combined path", and the caller falls back to
        ``_embed_dense`` + ``_embed_sparse``. A returned tuple is aligned 1:1 with ``texts`` on both
        axes. An implementer maps only the "route absent / unsupported" signal to None; a genuine
        transient failure must still be raised so the resilient wrapper can retry and split it.
        """
        _ = texts
        return None

    @staticmethod
    def __is_transient(error: Exception) -> bool:
        """A provider error worth retrying: a timeout, a transport blip, or a 429/5xx status."""
        if isinstance(error, httpx.TimeoutException | httpx.TransportError):
            return True
        return isinstance(error, httpx.HTTPStatusError) and error.response.status_code in (
            429,
            500,
            502,
            503,
            504,
        )

    async def __resilient(
        self,
        embed_fn: Callable[[list[str]], Awaitable[_Batch | None]],
        texts: list[str],
        concat: Callable[[_Batch, _Batch], _Batch],
    ) -> _Batch | None:
        """
        Call one provider embed hook with backoff-retry, then adaptive batch splitting.

        A single slow or transiently-failing batch must not lose the whole document (the previous
        behaviour: one timeout failed the embed node and discarded every vector already computed).
        So a transient error is retried with exponential backoff; if it still fails, the batch is
        halved and each half embedded independently — a smaller batch is lighter on a CPU-hosted
        model and usually succeeds. A single-text batch that still fails is a genuine error and is
        raised. max_retries=0 preserves the old one-shot behaviour (no retry, no split). Provider
        hooks return outputs aligned 1:1 with their input, so ``concat`` on the halves preserves
        order; a None sub-result (no sparse / no combined route) propagates as None. Shape-agnostic:
        the same skeleton serves the single-axis hook and the combined (dense, sparse) one.
        """
        config: BaseEmbedConfig = self.config
        if config.max_retries == 0:
            return await embed_fn(texts)
        for attempt in range(1, config.max_retries + 1):
            try:
                return await embed_fn(texts)
            except Exception as error:  # noqa: BLE001 — re-raised below unless transient
                if not self.__is_transient(error):
                    raise
                self.logger.warning(
                    f"Embedder '{self.KIND}' transient error on a {len(texts)}-text batch "
                    f"(attempt {attempt}/{config.max_retries}): {error!r}"
                )
                if attempt < config.max_retries:
                    await asyncio.sleep(config.retry_backoff_seconds * attempt)
        # Retries exhausted — split and embed the halves independently, or give up on a single text.
        if len(texts) <= 1:
            return await embed_fn(texts)
        mid = len(texts) // 2
        self.logger.warning(
            f"Embedder '{self.KIND}' still failing a {len(texts)}-text batch — splitting to "
            f"{mid} + {len(texts) - mid} and retrying each half"
        )
        left = await self.__resilient(embed_fn, texts[:mid], concat)
        right = await self.__resilient(embed_fn, texts[mid:], concat)
        if left is None or right is None:
            return None
        return concat(left, right)

    async def __resilient_batch(
        self,
        embed_fn: Callable[[list[str]], Awaitable[list]],
        texts: list[str],
    ) -> list | None:
        """Resilient single-axis embed: retry + split around one dense/sparse hook (see __resilient)."""
        return await self.__resilient(embed_fn, texts, lambda left, right: [*left, *right])

    async def __resilient_combined(
        self, texts: list[str]
    ) -> tuple[list[list[float]], list[SparseVector]] | None:
        """Resilient combined embed: the same retry + split skeleton around the single-pass hook.

        A None from ``_embed_dense_sparse`` means "no combined route" (unsupported) and propagates up
        so the batch loop can fall back to the two separate hooks — distinct from a raised transient
        error, which is retried and split like any other. On a split the halves' dense and sparse
        lists are concatenated independently, keeping each axis 1:1 with the input order.
        """
        return await self.__resilient(
            self._embed_dense_sparse,
            texts,
            lambda left, right: ([*left[0], *right[0]], [*left[1], *right[1]]),
        )

    async def __embed_all(
        self, texts: list[str], sparse: bool
    ) -> tuple[list[list[float]], list[SparseVector] | None]:
        """Run the batched dense (and optional sparse) embedding over every text.

        When sparse is requested, each batch first tries the provider's single-forward-pass combined
        hook; the first batch that reports it unsupported flips the run to the two separate hooks for
        every remaining batch (no re-probing /embed_all once it is known absent).
        """
        config: BaseEmbedConfig = self.config
        dense: list[list[float]] = []
        sparse_vectors: list[SparseVector] | None = [] if sparse else None
        combined_supported = sparse  # probe once; a None on the first sparse batch disables it
        for start in range(0, len(texts), config.batch_size):
            batch = texts[start : start + config.batch_size]
            if sparse_vectors is not None and combined_supported:
                combined = await self.__resilient_combined(batch)
                if combined is not None:
                    dense_batch, batch_sparse = combined
                    dense.extend(dense_batch)
                    sparse_vectors.extend(batch_sparse)
                    continue
                # Unsupported combined route — remember it and fall through to the separate hooks
                # for this batch and every later one.
                combined_supported = False
            dense_batch = await self.__resilient_batch(self._embed_dense, batch)
            dense.extend(dense_batch if dense_batch is not None else [])  # dense hook never None
            if sparse_vectors is not None:
                batch_sparse = await self.__resilient_batch(self._embed_sparse, batch)
                if batch_sparse is None:
                    if sparse_vectors:
                        # Earlier batches DID return sparse vectors — a mid-stream None would
                        # silently discard them and lose lexical vectors for part of the doc.
                        # Sparse support is a provider constant, so this is a contract breach: fail loud.
                        raise RuntimeError(
                            f"Embedder '{self.KIND}' returned sparse vectors for earlier batches "
                            f"but None for a later one — inconsistent sparse support"
                        )
                    # First batch: the provider has no sparse support — drop the whole axis, cleanly.
                    self.logger.info(f"Embedder '{self.KIND}' has no sparse support — dense only")
                    sparse_vectors = None
                else:
                    sparse_vectors.extend(batch_sparse)
        return dense, sparse_vectors

    async def __embed_semantic_fields(
        self, chunks: list[Chunk], contract: CollectionContract
    ) -> dict[str, dict[int, list[float]]]:
        """Per-field vectors of the SEMANTIC chunk fields → {field: {chunk index: vector}}."""
        semantic_fields = [
            spec.field_name
            for spec in contract.fields
            if spec.semantic and spec.scope == FieldScope.CHUNK
        ]
        vectors: dict[str, dict[int, list[float]]] = {}
        for field_name in semantic_fields:
            # 1. Only chunks that carry a value; lists render as comma-joined text.
            indexed: list[tuple[int, str]] = []
            for index, chunk in enumerate(chunks):
                value = chunk.generated_meta.get(field_name)
                if value is None:
                    continue
                text = ", ".join(value) if isinstance(value, list) else str(value)
                if text.strip():
                    indexed.append((index, text))
            if not indexed:
                continue
            # 2. One batched pass per field, mapped back to the chunk indexes.
            dense, _ = await self.__embed_all([text for _, text in indexed], sparse=False)
            vectors[field_name] = {
                index: vector for (index, _), vector in zip(indexed, dense, strict=True)
            }
        return vectors

    async def run(self, data: EmbedConsumes) -> EmbedProduces:
        """
        Embed every ENABLED chunk (enriched text) + the semantic field values.

        Only chunks whose role is enabled by default are embedded — furniture (header/footer, toc)
        gets no vectors and no spend. Disabled chunks keep flowing to persistence via the chunk
        artefact; they are simply absent from the chunk_id-linked vectors here.

        Args:
            data (EmbedConsumes): The final chunks + the contract.

        Returns:
            EmbedProduces: One ChunkVectors per ENABLED chunk, chunk_id-linked, in chunk order.
        """
        config: BaseEmbedConfig = self.config
        # 1. THE single policy: embed only role-default-enabled chunks (body); skip the furniture.
        #    Then drop content-free chunks (bare figure placeholders): like the role-disabled ones
        #    they still flow to persistence via the chunk artefact, but they get NO vector — so a
        #    placeholder can never surface as a search hit with a misleading self-citation.
        enabled = [
            chunk
            for chunk in data.chunks
            if role_default_enabled(chunk.role)
            and self._has_searchable_content(chunk.enriched_text)
        ]
        if not enabled:
            return EmbedProduces(embeddings=ChunkEmbeddings(model=config.model))

        # 2. The main pair: the ENRICHED text of every enabled chunk, batched.
        texts = [chunk.enriched_text for chunk in enabled]
        dense, sparse_vectors = await self.__embed_all(texts, sparse=config.embed_sparse)

        # 3. The named per-field vectors of the semantic chunk fields (enabled chunks only).
        field_vectors = (
            await self.__embed_semantic_fields(enabled, data.contract)
            if config.embed_semantic_fields
            else {}
        )

        # 4. Assemble, chunk_id-linked, in enabled-chunk order.
        items = [
            ChunkVectors(
                chunk_id=chunk.chunk_id,
                dense=dense[index],
                sparse=sparse_vectors[index] if sparse_vectors is not None else None,
                fields={
                    field_name: per_chunk[index]
                    for field_name, per_chunk in field_vectors.items()
                    if index in per_chunk
                },
            )
            for index, chunk in enumerate(enabled)
        ]
        self.logger.info(
            f"Embedded {len(items)}/{len(data.chunks)} chunk(s) "
            f"({len(data.chunks) - len(enabled)} skipped by role or empty content) "
            f"(dense dim {len(dense[0])}, sparse: {sparse_vectors is not None}, "
            f"semantic fields: {sorted(field_vectors)})"
        )
        return EmbedProduces(
            embeddings=ChunkEmbeddings(model=config.model, dimension=len(dense[0]), items=items)
        )


__all__ = ["BaseEmbedderNode"]
