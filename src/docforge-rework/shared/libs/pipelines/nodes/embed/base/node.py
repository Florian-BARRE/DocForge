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
from abc import abstractmethod

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


class BaseEmbedderNode(ActionNode):
    """Abstract embedder: chunks in, chunk-linked vectors out; children implement the hooks."""

    Consumes = EmbedConsumes
    Produces = EmbedProduces

    @abstractmethod
    async def _embed_dense(self, texts: list[str]) -> list[list[float]]:
        """Embed one batch of texts into dense vectors (same order)."""
        ...

    async def _embed_sparse(self, texts: list[str]) -> list[SparseVector] | None:
        """Embed one batch into sparse vectors — None when the provider has none (default)."""
        _ = texts
        return None

    def _wants_colbert(self) -> bool:
        """Whether this provider should also produce ColBERT multi-vectors (default: no).

        The colbert axis is opt-in and provider-specific: a provider overrides this to expose the
        collection's single source of truth. When False, __embed_colbert is never invoked — zero cost.
        """
        return False

    async def _embed_colbert(self, texts: list[str]) -> list[list[list[float]]]:
        """Embed one batch into ColBERT multi-vectors — one token-vector matrix per input, in order.

        Only called when _wants_colbert() is True; the base has no colbert provider.
        """
        raise NotImplementedError(f"Embedder '{self.KIND}' has no ColBERT support")

    async def __embed_all(self, texts: list[str], sparse: bool) -> tuple[list[list[float]], list[SparseVector] | None]:
        """Run the batched dense (and optional sparse) embedding over every text."""
        config: BaseEmbedConfig = self.config
        dense: list[list[float]] = []
        sparse_vectors: list[SparseVector] | None = [] if sparse else None
        for start in range(0, len(texts), config.batch_size):
            batch = texts[start: start + config.batch_size]
            dense.extend(await self._embed_dense(batch))
            if sparse_vectors is not None:
                batch_sparse = await self._embed_sparse(batch)
                if batch_sparse is None:
                    # The provider has no sparse support — drop the whole axis, once, loudly.
                    self.logger.info(f"Embedder '{self.KIND}' has no sparse support — dense only")
                    sparse_vectors = None
                else:
                    sparse_vectors.extend(batch_sparse)
        return dense, sparse_vectors

    async def __embed_colbert_all(self, texts: list[str]) -> list[list[list[float]]]:
        """Run the batched ColBERT embedding over every text, preserving order."""
        config: BaseEmbedConfig = self.config
        colbert: list[list[list[float]]] = []
        for start in range(0, len(texts), config.batch_size):
            batch = texts[start: start + config.batch_size]
            colbert.extend(await self._embed_colbert(batch))
        return colbert

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
            vectors[field_name] = {index: vector for (index, _), vector in zip(indexed, dense, strict=True)}
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
        enabled = [chunk for chunk in data.chunks if role_default_enabled(chunk.role)]
        if not enabled:
            return EmbedProduces(embeddings=ChunkEmbeddings(model=config.model))

        # 2. The main pair: the ENRICHED text of every enabled chunk, batched.
        texts = [chunk.enriched_text for chunk in enabled]
        dense, sparse_vectors = await self.__embed_all(texts, sparse=config.embed_sparse)

        # 3. The optional ColBERT multi-vectors — SAME texts, same order, so they align 1:1 with
        #    dense by index/chunk_id. Opt-in and provider-specific: nothing runs when not wanted.
        colbert_vectors = await self.__embed_colbert_all(texts) if self._wants_colbert() else None

        # 4. The named per-field vectors of the semantic chunk fields (enabled chunks only).
        field_vectors = (
            await self.__embed_semantic_fields(enabled, data.contract)
            if config.embed_semantic_fields
            else {}
        )

        # 5. Assemble, chunk_id-linked, in enabled-chunk order.
        items = [
            ChunkVectors(
                chunk_id=chunk.chunk_id,
                dense=dense[index],
                sparse=sparse_vectors[index] if sparse_vectors is not None else None,
                colbert=colbert_vectors[index] if colbert_vectors is not None else None,
                fields={
                    field_name: per_chunk[index]
                    for field_name, per_chunk in field_vectors.items()
                    if index in per_chunk
                },
            )
            for index, chunk in enumerate(enabled)
        ]
        # Derive from the first NON-EMPTY token matrix: colbert token counts are variable, so a
        # degenerate leading chunk (empty matrix) must not null the dim while later points carry vectors.
        colbert_dim = (
            next((len(matrix[0]) for matrix in colbert_vectors if matrix), None)
            if colbert_vectors
            else None
        )
        self.logger.info(
            f"Embedded {len(items)}/{len(data.chunks)} chunk(s) "
            f"({len(data.chunks) - len(enabled)} skipped by role) "
            f"(dense dim {len(dense[0])}, sparse: {sparse_vectors is not None}, "
            f"colbert dim: {colbert_dim}, semantic fields: {sorted(field_vectors)})"
        )
        return EmbedProduces(
            embeddings=ChunkEmbeddings(
                model=config.model, dimension=len(dense[0]), colbert_dim=colbert_dim, items=items
            )
        )


__all__ = ["BaseEmbedderNode"]
