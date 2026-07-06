# ====== Code Summary ======
# BaseEmbedderNode — the abstract base of every embedder. The shared frame: batch the chunks'
# ENRICHED texts through the provider hooks (dense required, sparse optional), then embed the
# SEMANTIC chunk-field values as named per-field vectors, and assemble the chunk-linked output.
# Embedding is NOT optional (a chunk without vectors cannot be indexed): any provider failure
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
        Embed every chunk (enriched text) + the semantic field values.

        Args:
            data (EmbedConsumes): The final chunks + the contract.

        Returns:
            EmbedProduces: One ChunkVectors per chunk, chunk_id-linked, in chunk order.
        """
        config: BaseEmbedConfig = self.config
        if not data.chunks:
            return EmbedProduces(embeddings=ChunkEmbeddings(model=config.model))

        # 1. The main pair: the ENRICHED text of every chunk, batched.
        texts = [chunk.enriched_text for chunk in data.chunks]
        dense, sparse_vectors = await self.__embed_all(texts, sparse=config.embed_sparse)

        # 2. The named per-field vectors of the semantic chunk fields.
        field_vectors = (
            await self.__embed_semantic_fields(data.chunks, data.contract)
            if config.embed_semantic_fields
            else {}
        )

        # 3. Assemble, chunk_id-linked, in chunk order.
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
            for index, chunk in enumerate(data.chunks)
        ]
        self.logger.info(
            f"Embedded {len(items)} chunk(s) "
            f"(dense dim {len(dense[0])}, sparse: {sparse_vectors is not None}, "
            f"semantic fields: {sorted(field_vectors)})"
        )
        return EmbedProduces(
            embeddings=ChunkEmbeddings(model=config.model, dimension=len(dense[0]), items=items)
        )


__all__ = ["BaseEmbedderNode"]
