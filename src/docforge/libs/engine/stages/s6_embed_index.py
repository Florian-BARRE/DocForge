# ====== Code Summary ======
# S6 — Embedding and Qdrant indexing stage (multi-field hybrid, spec §7.2).
# Embeds the chunk body (content) plus one named dense vector per `semantic` metadata field
# and one sparse vector per `lexical` field, upserts them to Qdrant, and persists chunks to
# Postgres. The metadata schema + per-document field values drive which vectors are built.

# ====== Standard Library Imports ======
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

# ====== Third-Party Library Imports ======
from loggerplusplus import LoggerClass
from sqlalchemy.ext.asyncio import AsyncSession

from libs.capabilities.chain import Chain, chain_outcome_to_attempt_dicts

# ====== Internal Project Imports ======
from libs.core.ir.chunk import Chunk
from libs.core.ir.models import ChainAttemptIR, ChainTrace
from libs.data.retrieval.field_index import (
    CONTENT_DENSE,
    CONTENT_SPARSE,
    FieldIndexHelpers,
)
from libs.data.storage.postgres.repositories.chunk_repo import ChunkRepository
from libs.data.storage.qdrant.client import QdrantStorageClient

# ====== Local Project Imports ======
from .s6_helpers import S6IndexHelpers


@dataclass(slots=True)
class S6Result:
    """
    Output of the S6 embedding and indexing stage.

    Attributes:
        n_embedded (int): Number of chunks passed through the embedding model (content).
        n_upserted_qdrant (int): Number of points upserted to Qdrant.
        n_inserted_postgres (int): Number of chunk rows inserted into Postgres.
        collection_name (str): Qdrant collection name used for the upsert.
        n_field_vectors (int): Number of per-field named vectors materialized.
        chain_traces (list[ChainTrace]): Per-batch embed chain traces; the engine
            appends them onto ``DocumentIR.chain_traces`` for full lineage.
    """

    n_embedded: int
    n_upserted_qdrant: int
    n_inserted_postgres: int
    collection_name: str
    n_field_vectors: int = 0
    chain_traces: list[ChainTrace] = field(default_factory=list)


class S6EmbedIndexStage(LoggerClass):
    """
    S6 — Embed and index with multi-field hybrid vectors.

    Per chunk it materializes:
    - ``content_dense`` / ``content_bm25`` — the chunk body (always).
    - ``meta_<field>_dense`` — for each ``semantic`` field (the field value embedded).
    - ``meta_<field>_bm25`` — for each ``lexical`` field (the field value as sparse BM25).
    Filterable field values go into the Qdrant payload. Both Qdrant and Postgres writes are
    idempotent, preserving the incremental-reindex property.
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
        self._embed_chain = embed_chain
        self._qdrant = qdrant
        self._chunk_repo = chunk_repo
        self._embed_batch_size = embed_batch_size
        self._batch_traces: list[ChainTrace] = []

    @property
    def embed_chain(self) -> Chain[Any, Any]:
        """Expose the chain so the engine can fingerprint its signature."""
        return self._embed_chain

    @property
    def dimension(self) -> int:
        """Return the dimension of the first embed provider (used by ensure_collection)."""
        first = self._embed_chain.providers[0] if self._embed_chain.providers else None
        return int(getattr(first, "dimension", 0))

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
        self._batch_traces = []

        doc_meta = doc_meta or {}
        plan = FieldIndexHelpers.derive_vector_plan(metadata_fields or [])

        # 0. Hierarchical mode: parents (referenced by a child's parent_id) carry the full section
        #    text for context but are NOT indexed in Qdrant — only their children are searched.
        #    Every chunk (parents included) is still persisted to Postgres for hydration.
        parent_ids = {c.parent_id for c in chunks if c.parent_id}
        index_chunks = [c for c in chunks if c.id not in parent_ids]

        # 1. Embed the chunk body (content_dense + content_bm25) for the indexed chunks
        content_dense, content_sparse = await self._embed_texts([c.embed_text for c in index_chunks])

        # 2. Embed each metadata field's per-chunk value once (reused for dense and/or sparse)
        field_names: list[str] = []
        for fv in [*plan.dense, *plan.sparse]:
            if fv.name not in field_names:
                field_names.append(fv.name)
        field_dense: dict[str, list[list[float] | None]] = {}
        field_sparse: dict[str, list[dict[int, float] | None]] = {}
        for name in field_names:
            values = [FieldIndexHelpers.resolve_field_text(name, c, doc_meta) for c in index_chunks]
            d, sp = await self._embed_values(values)
            field_dense[name] = d
            field_sparse[name] = sp

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
            chain_traces=list(self._batch_traces),
        )

    # ─── Internal ─────────────────────────────────────────────────────────────

    async def _embed_texts(
        self, texts: list[str]
    ) -> tuple[list[list[float]], list[dict[int, float]] | None]:
        """
        Embed a list of texts via the embed chain, batched per ``embed_batch_size``.

        Each batch contributes one ``ChainTrace`` to ``self._batch_traces``; the engine
        flushes them onto the document IR after the stage returns.

        Raises:
            RuntimeError: When the chain exhausts every provider for a batch.
        """
        all_dense: list[list[float]] = []
        all_sparse: list[dict[int, float]] | None = None
        for i in range(0, len(texts), self._embed_batch_size):
            batch = texts[i : i + self._embed_batch_size]
            outcome = await self._embed_chain.call(lambda p: p.embed(batch))
            self._batch_traces.append(ChainTrace(
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

    async def _embed_values(
        self, values: list[str | None]
    ) -> tuple[list[list[float] | None], list[dict[int, float] | None]]:
        """
        Embed only the non-empty field values, scattering results back per chunk.

        Chunks with no value for the field get None (→ no named vector on that point).
        """
        dense_out: list[list[float] | None] = [None] * len(values)
        sparse_out: list[dict[int, float] | None] = [None] * len(values)
        idxs = [i for i, v in enumerate(values) if v]
        if not idxs:
            return dense_out, sparse_out
        dense, sparse = await self._embed_texts([values[i] or "" for i in idxs])
        for j, i in enumerate(idxs):
            dense_out[i] = dense[j]
            if sparse is not None:
                sparse_out[i] = sparse[j]
        return dense_out, sparse_out

