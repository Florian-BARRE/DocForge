# ====== Code Summary ======
# BaseEmbedderNode — the abstract base of every embedder. The shared frame: keep only the chunks
# whose role is enabled by default (role_default_enabled is THE single policy: body embeds, furniture
# like header/footer & toc does not), batch their ENRICHED texts through the provider hooks, embed the
# SEMANTIC / LEXICAL chunk-field values as named per-field vectors, and assemble the chunk-linked
# output. Which axes run, and how, is decided by small overridable hooks: a dense axis and/or a sparse
# axis; the two in ONE combined call when the provider can; else the two axes concurrently (each under
# its own endpoint policy) or sequentially. Every call goes through the ResilientEmbedCalls retry/split
# + limiter frame. Disabled chunks simply get NO vectors. Any provider failure fails the node.

# ====== Standard Library Imports ======
import asyncio
import re
from abc import abstractmethod

# ====== Internal Project Imports ======
from shared_libs.pipelines.base import ActionNode, NodeUsage
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
from .io import EmbedConsumes, EmbedProduces
from .policy import EmbedCallPolicy
from .resilience import ResilientEmbedCalls

# A bare figure marker line — an "[Image: <kind>]" with NOTHING after the closing bracket.
_BARE_IMAGE_MARKER = re.compile(r"^\[Image:[^\]]*\]$")

_DENSE = "dense"
_SPARSE = "sparse"
_COMBINED = "combined"


def _concat_pair(left: tuple, right: tuple) -> tuple:
    """Concatenate two (dense, sparse) halves axis by axis, keeping each 1:1 with the input."""
    return [*left[0], *right[0]], [*left[1], *right[1]]


class BaseEmbedderNode(ResilientEmbedCalls, ActionNode):
    """Abstract embedder: chunks in, chunk-linked vectors out; children implement the hooks."""

    Consumes = EmbedConsumes
    Produces = EmbedProduces

    # Running paid-call token usage for THIS run (a local/free embedder leaves it None).
    _last_usage: NodeUsage | None = None

    @staticmethod
    def _has_searchable_content(text: str) -> bool:
        """Whether an enriched text carries anything beyond whitespace / bare ``[Image: …]`` markers."""
        for line in text.splitlines():
            stripped = line.strip()
            if stripped and not _BARE_IMAGE_MARKER.match(stripped):
                return True
        return False

    @staticmethod
    def __indexed_field_values(chunks: list[Chunk], field_name: str) -> list[tuple[int, str]]:
        """The (chunk index, text) pairs of the chunks carrying a non-blank value for a field."""
        indexed: list[tuple[int, str]] = []
        for index, chunk in enumerate(chunks):
            value = chunk.generated_meta.get(field_name)
            if value is None:
                continue
            text = ", ".join(value) if isinstance(value, list) else str(value)
            if text.strip():
                indexed.append((index, text))
        return indexed

    # ---------------------------------------------------------------- provider hooks (override)

    @abstractmethod
    async def _embed_dense(self, texts: list[str]) -> list[list[float]]:
        """Embed one batch into dense vectors (same order) — a sparse-only embedder raises."""

    async def _embed_sparse(self, texts: list[str]) -> list[SparseVector] | None:
        """Embed one batch of CONTENT into sparse vectors — None when the provider has none."""
        _ = texts
        return None

    async def _embed_sparse_fields(self, texts: list[str]) -> list[SparseVector] | None:
        """Sparse vectors of short METADATA values (same as content unless a provider tells apart)."""
        return await self._embed_sparse(texts)

    async def _embed_query_sparse(self, text: str) -> SparseVector | None:
        """The query-side sparse vector (same as the document side unless overridden)."""
        vectors = await self._embed_sparse([text])
        return vectors[0] if vectors else None

    async def _embed_dense_sparse(
        self, texts: list[str]
    ) -> tuple[list[list[float]], list[SparseVector]] | None:
        """Both axes in ONE call — None (default) means "no combined path", use two calls."""
        _ = texts
        return None

    # ---------------------------------------------------------------- axis plan (override)

    def has_dense(self) -> bool:
        """Whether this embedder produces dense vectors."""
        return True

    def has_sparse(self) -> bool:
        """Whether this embedder is asked for sparse vectors (a provider may still return None)."""
        return bool(getattr(self.config, "embed_sparse", True))

    def sparse_idf(self) -> bool:
        """Whether the sparse vectors are term frequencies needing the store's IDF modifier."""
        return False

    def model_name(self) -> str:
        """The model identity stamped on the produced embeddings (provenance)."""
        return str(getattr(self.config, "model", ""))

    def _call_policy(self, axis: str) -> EmbedCallPolicy:
        """The retry/limiter policy of one call site (``dense`` / ``sparse`` / ``combined``)."""
        _ = axis
        return EmbedCallPolicy.from_config(self.config)

    def _parallel_axes(self) -> bool:
        """Whether two separate axis calls run concurrently (independent endpoints) — default no."""
        return False

    def _collect_usage(self) -> NodeUsage | None:
        """The paid-call usage to stamp on the output (default: the running accumulator)."""
        return self._last_usage

    # ---------------------------------------------------------------- batching

    async def __axis(self, axis: str, batch: list[str]) -> list | None:
        """One resilient single-axis call (dense or sparse) under that axis's policy."""
        hook = self._embed_dense if axis == _DENSE else self._embed_sparse
        return await self._resilient(
            hook, batch, lambda left, right: [*left, *right], self._call_policy(axis)
        )

    async def __two_axes(self, batch: list[str]) -> tuple[list | None, list | None]:
        """Dense + sparse as two calls — concurrent on independent endpoints, else sequential."""
        if self._parallel_axes():
            dense, sparse = await asyncio.gather(
                self.__axis(_DENSE, batch), self.__axis(_SPARSE, batch)
            )
            return dense, sparse
        return await self.__axis(_DENSE, batch), await self.__axis(_SPARSE, batch)

    def __accept_sparse(
        self, collected: list[SparseVector] | None, batch_sparse: list | None
    ) -> list[SparseVector] | None:
        """Fold one batch's sparse output in; a first-batch None drops the axis cleanly."""
        if collected is None:
            return None
        if batch_sparse is not None:
            collected.extend(batch_sparse)
            return collected
        if collected:
            # Sparse support is a provider constant — a mid-stream None would lose earlier vectors.
            raise RuntimeError(
                f"Embedder '{self.KIND}' returned sparse vectors for earlier batches but None for "
                f"a later one — inconsistent sparse support"
            )
        self.logger.info(f"Embedder '{self.KIND}' has no sparse support — no sparse vectors")
        return None

    async def __embed_all(
        self, texts: list[str], dense_on: bool, sparse_on: bool
    ) -> tuple[list[list[float]], list[SparseVector] | None]:
        """Batch every text through the planned axes (combined when possible, else per axis)."""
        batch_size = int(getattr(self.config, "batch_size", 32))
        dense: list[list[float]] = []
        sparse: list[SparseVector] | None = [] if sparse_on else None
        combined_ok = dense_on and sparse_on
        for start in range(0, len(texts), batch_size):
            batch = texts[start : start + batch_size]
            # 1. Both axes from one server: ONE call per batch (one limiter slot); a None on the
            #    first batch means the route is absent → separate calls for this and later batches.
            if combined_ok and sparse is not None:
                combined = await self._resilient(
                    self._embed_dense_sparse, batch, _concat_pair, self._call_policy(_COMBINED)
                )
                if combined is not None:
                    dense.extend(combined[0])
                    sparse.extend(combined[1])
                    continue
                combined_ok = False
            # 2. Separate axis calls.
            if dense_on and sparse is not None:
                batch_dense, batch_sparse = await self.__two_axes(batch)
            else:
                batch_dense = await self.__axis(_DENSE, batch) if dense_on else None
                batch_sparse = await self.__axis(_SPARSE, batch) if sparse is not None else None
            dense.extend(batch_dense or [])
            sparse = self.__accept_sparse(sparse, batch_sparse)
        return dense, sparse

    async def __field_vectors(
        self, chunks: list[Chunk], contract: CollectionContract, lexical: bool
    ) -> dict[str, dict[int, object]]:
        """Per-field vectors of the chunk-scope SEMANTIC (dense) or LEXICAL (sparse) fields."""
        names = [
            spec.field_name
            for spec in contract.fields
            if (spec.lexical if lexical else spec.semantic) and spec.scope == FieldScope.CHUNK
        ]
        vectors: dict[str, dict[int, object]] = {}
        policy = self._call_policy(_SPARSE if lexical else _DENSE)
        hook = self._embed_sparse_fields if lexical else self._embed_dense
        batch_size = int(getattr(self.config, "batch_size", 32))
        for field_name in names:
            indexed = self.__indexed_field_values(chunks, field_name)
            if not indexed:
                continue
            texts = [text for _, text in indexed]
            out: list = []
            for start in range(0, len(texts), batch_size):
                part = await self._resilient(
                    hook, texts[start : start + batch_size], lambda a, b: [*a, *b], policy
                )
                if part is None:  # no sparse axis on this provider — the field gets no vector
                    out = []
                    break
                out.extend(part)
            if out:
                vectors[field_name] = {i: v for (i, _), v in zip(indexed, out, strict=True)}
        return vectors

    def __embeddings(
        self, dimension: int, items: list[ChunkVectors], sparse: bool
    ) -> ChunkEmbeddings:
        """The output artefact, carrying the vector layout the store must declare."""
        return ChunkEmbeddings(
            model=self.model_name(),
            dimension=dimension,
            items=items,
            dense_enabled=self.has_dense(),
            sparse_enabled=sparse,
            sparse_idf=sparse and self.sparse_idf(),
        )

    # ---------------------------------------------------------------- public entry points

    async def encode_query_dense(self, text: str) -> list[float]:
        """Encode one query into its dense vector (no retry/split — the caller bounds the call)."""
        return (await self._embed_dense([text]))[0]

    async def encode_query_sparse(self, text: str) -> SparseVector | None:
        """Encode one query into its sparse vector, or None when the embedder has no sparse axis."""
        return await self._embed_query_sparse(text)

    async def run(self, data: EmbedConsumes) -> EmbedProduces:
        """
        Embed every ENABLED chunk (enriched text) + the chunk-scope semantic/lexical field values.

        Args:
            data (EmbedConsumes): The final chunks + the contract.

        Returns:
            EmbedProduces: One ChunkVectors per ENABLED chunk, chunk_id-linked, in chunk order.
        """
        # 0. Reset the per-run usage accumulator (a paid hook folds its tokens in below).
        self._last_usage = None
        dense_on, sparse_on = self.has_dense(), self.has_sparse()
        # 1. THE single policy: embed only role-default-enabled chunks with real content.
        enabled = [
            chunk
            for chunk in data.chunks
            if role_default_enabled(chunk.role)
            and self._has_searchable_content(chunk.enriched_text)
        ]
        if not enabled:
            empty = EmbedProduces(embeddings=self.__embeddings(0, [], sparse_on))
            empty._usage = self._collect_usage()
            return empty

        # 2. The content vectors of every enabled chunk, batched through the planned axes.
        texts = [chunk.enriched_text for chunk in enabled]
        dense, sparse = await self.__embed_all(texts, dense_on, sparse_on)

        # 3. Per-field vectors, each gated by its switch AND by the axis it needs.
        semantic = bool(getattr(self.config, "embed_semantic_fields", False)) and dense_on
        lexical = bool(getattr(self.config, "embed_lexical_fields", False)) and sparse is not None
        fields = await self.__field_vectors(enabled, data.contract, False) if semantic else {}
        field_sparse = await self.__field_vectors(enabled, data.contract, True) if lexical else {}

        # 4. Assemble, chunk_id-linked, in enabled-chunk order.
        items = [
            ChunkVectors(
                chunk_id=chunk.chunk_id,
                dense=dense[index] if dense else None,
                sparse=sparse[index] if sparse is not None else None,
                fields={n: per[index] for n, per in fields.items() if index in per},
                field_sparse={n: per[index] for n, per in field_sparse.items() if index in per},
            )
            for index, chunk in enumerate(enabled)
        ]
        dimension = len(dense[0]) if dense else 0
        self.logger.info(
            f"Embedded {len(items)}/{len(data.chunks)} chunk(s) "
            f"({len(data.chunks) - len(enabled)} skipped by role or empty content) "
            f"(dense dim {dimension}, sparse: {sparse is not None}, "
            f"semantic fields: {sorted(fields)}, lexical fields: {sorted(field_sparse)})"
        )
        output = EmbedProduces(embeddings=self.__embeddings(dimension, items, sparse is not None))
        output._usage = self._collect_usage()
        return output


__all__ = ["BaseEmbedderNode"]
