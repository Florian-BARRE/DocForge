# ====== Code Summary ======
# S6 — Embedding and Qdrant indexing stage (multi-field hybrid, spec §7.2).
# Embeds the chunk body (content) plus one named dense vector per `semantic` metadata field
# and one sparse vector per `lexical` field, upserts them to Qdrant, and persists chunks to
# Postgres. The metadata schema + per-document field values drive which vectors are built.
# Batched embedding is delegated to S6Embedder (s6_embedder.py).

# ====== Standard Library Imports ======
from __future__ import annotations

from typing import Any

# ====== Third-Party Library Imports ======
from loggerplusplus import LoggerClass
from sqlalchemy.ext.asyncio import AsyncSession

from libs.providers.chain import Chain

# ====== Internal Project Imports ======
from libs.domain.ir.chunk import Chunk
from libs.search.field_index import (
    CONTENT_DENSE,
    CONTENT_SPARSE,
    FieldIndexHelpers,
)
from libs.storage.postgres.repositories.chunk_repo import ChunkRepository
from libs.storage.qdrant.client import QdrantStorageClient

# ====== Local Project Imports ======
from .embedder import S6Embedder
from .helpers import S6IndexHelpers
from .result import S6Result


class S6EmbedIndexStage(LoggerClass):
    """
    S6 — Embed and index with multi-field hybrid vectors.

    Per chunk it materializes:
    - ``content_dense`` / ``content_bm25`` — the chunk body (always).
    - ``meta_<field>_dense`` — for each ``semantic`` field (the field value embedded).
    - ``meta_<field>_bm25`` — for each ``lexical`` field (the field value as sparse BM25).
    Filterable field values go into the Qdrant payload. Both Qdrant and Postgres writes are
    idempotent, preserving the incremental-reindex property.  Batched embedding lives in
    ``S6Embedder``.
    """

    def __init__(
        self,
        embed_chain: Chain[Any, Any],
        qdrant: QdrantStorageClient,
        chunk_repo: ChunkRepository,
        embed_batch_size: int = 64,
    ) -> None:
        """
        Initialize S6.

        Args:
            embed_chain (Chain[EmbedProvider, EmbedResult]): Ordered embed chain.
                Index 0 is tried first; the gate escalates when a provider raises.
            qdrant (QdrantStorageClient): Async Qdrant client.
            chunk_repo (ChunkRepository): Postgres chunk repository.
            embed_batch_size (int): Texts sent per chain attempt.
        """
        LoggerClass.__init__(self)
        self._embedder = S6Embedder(embed_chain, embed_batch_size)
        self._qdrant = qdrant
        self._chunk_repo = chunk_repo

    @property
    def embed_chain(self) -> Chain[Any, Any]:
        """Expose the chain so the engine can fingerprint its signature."""
        return self._embedder.embed_chain

    @property
    def dimension(self) -> int:
        """Return the dimension of the first embed provider (used by ensure_collection)."""
        return self._embedder.dimension

    async def run(
        self,
        chunks: list[Chunk],
        collection_name: str,
        session: AsyncSession,
        metadata_fields: list[Any] | None = None,
        doc_meta: dict[str, Any] | None = None,
    ) -> S6Result:
        """
        Embed, index to Qdrant (multi-field hybrid), and persist to Postgres.

        Args:
            chunks (list[Chunk]): Contextualized chunks from S5 (embed_text populated).
            collection_name (str): Qdrant collection to upsert into.
            session (AsyncSession): Active Postgres session for chunk persistence.
            metadata_fields (list | None): Collection metadata field defs (3-flags + weights).
            doc_meta (dict | None): Document-level field values (implicit + user meta).

        Returns:
            S6Result: Counts of embedded, upserted, inserted items + field-vector count.
        """
        self.logger.info(f"S6 started: chunks={len(chunks)} collection={collection_name!r}")
        if not chunks:
            return S6Result(0, 0, 0, collection_name)

        # Reset per-run trace accumulator; each batch contributes one ChainTrace.
        self._embedder.begin_run()

        doc_meta = doc_meta or {}
        plan = FieldIndexHelpers.derive_vector_plan(metadata_fields or [])

        # 0. Hierarchical mode: parents (referenced by a child's parent_id) carry the full section
        #    text for context but are NOT indexed in Qdrant — only their children are searched.
        #    Every chunk (parents included) is still persisted to Postgres for hydration.
        parent_ids = {c.parent_id for c in chunks if c.parent_id}
        index_chunks = [c for c in chunks if c.id not in parent_ids]

        # 1. Embed the chunk body (content_dense + content_bm25) for the indexed chunks
        content_dense, content_sparse = await self._embedder.embed_texts(
            [c.embed_text for c in index_chunks]
        )

        # 2. Embed each metadata field's per-chunk value once (reused for dense and/or sparse)
        field_dense, field_sparse = await self._embed_fields(plan, index_chunks, doc_meta)

        # 3. Ensure the collection carries every named vector the schema needs
        await self._qdrant.ensure_collection(
            collection_name,
            dense_dim=self.dimension,
            field_dense_names=plan.dense_vector_names,
            field_sparse_names=plan.sparse_vector_names,
        )

        # 4. Assemble named-vector maps (content + per field)
        dense_by_vector: dict[str, list[list[float] | None]] = {CONTENT_DENSE: content_dense}
        for fv in plan.dense:
            dense_by_vector[fv.vector] = field_dense[fv.name]
        sparse_by_vector: dict[str, list[dict[int, float] | None]] = {}
        if content_sparse is not None:
            sparse_by_vector[CONTENT_SPARSE] = content_sparse
        for fv in plan.sparse:
            sparse_by_vector[fv.vector] = field_sparse[fv.name]

        # 5. Upsert the indexed chunks to Qdrant + persist ALL chunks to Postgres (both idempotent)
        payloads = [S6IndexHelpers.build_payload(c, metadata_fields or [], doc_meta) for c in index_chunks]
        n_upserted = await self._qdrant.upsert_points(
            collection_name=collection_name,
            chunk_ids=[c.id for c in index_chunks],
            dense_by_vector=dense_by_vector,
            sparse_by_vector=sparse_by_vector,
            payloads=payloads,
        )
        await self._chunk_repo.bulk_insert(session, chunks)

        n_field_vectors = len(plan.dense) + len(plan.sparse)
        self.logger.info(
            f"S6 done: embedded={len(index_chunks)} qdrant={n_upserted} persisted={len(chunks)} "
            f"field_vectors={n_field_vectors} collection={collection_name!r}"
        )
        return S6Result(
            len(index_chunks), n_upserted, len(chunks), collection_name, n_field_vectors,
            chain_traces=list(self._embedder.batch_traces),
        )

    # ─── Internal ─────────────────────────────────────────────────────────────

    async def _embed_fields(
        self,
        plan: Any,
        index_chunks: list[Chunk],
        doc_meta: dict[str, Any],
    ) -> tuple[dict[str, list[list[float] | None]], dict[str, list[dict[int, float] | None]]]:
        """
        Embed each unique metadata field's per-chunk value once.

        A field appearing in both the dense and sparse plans is embedded a single time;
        the dense and sparse projections are reused for every vector that references it.

        Args:
            plan (Any): Vector plan from FieldIndexHelpers.derive_vector_plan.
            index_chunks (list[Chunk]): The chunks being indexed (parents excluded).
            doc_meta (dict[str, Any]): Document-level field values.

        Returns:
            tuple: ``(field_dense, field_sparse)`` keyed by field name.
        """
        field_names: list[str] = []
        for fv in [*plan.dense, *plan.sparse]:
            if fv.name not in field_names:
                field_names.append(fv.name)
        field_dense: dict[str, list[list[float] | None]] = {}
        field_sparse: dict[str, list[dict[int, float] | None]] = {}
        for name in field_names:
            values = [FieldIndexHelpers.resolve_field_text(name, c, doc_meta) for c in index_chunks]
            d, sp = await self._embedder.embed_values(values)
            field_dense[name] = d
            field_sparse[name] = sp
        return field_dense, field_sparse
