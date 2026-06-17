# ====== Code Summary ======
# Async Qdrant client wrapper for DocForge hybrid vector store operations.
# Manages collection lifecycle, hybrid upserts (dense + sparse), and hybrid search.
# Qdrant is the retrieval index — never the source of truth (that's Postgres).

# ====== Standard Library Imports ======
from __future__ import annotations

from typing import Any

# ====== Third-Party Library Imports ======
from loggerplusplus import LoggerClass
from qdrant_client import AsyncQdrantClient
from qdrant_client.models import (
    Distance,
    Filter,
    PointIdsList,
    PointStruct,
    PointVectors,
    SparseVector,
    SparseVectorParams,
    VectorParams,
)

# ====== Internal Project Imports ======
from retrieval.field_index import CONTENT_DENSE, CONTENT_SPARSE, FieldIndexHelpers


# Named content vector keys (always present). Per-field vectors are named meta_<field>_dense
# / meta_<field>_bm25 (see libs/retrieval/field_index.py — one source of truth).
DENSE_VECTOR_NAME: str = CONTENT_DENSE
SPARSE_VECTOR_NAME: str = CONTENT_SPARSE

# BGE-M3 dense dimension (fixed per model version)
BGE_M3_DIMENSION: int = 1024


class QdrantStorageClient(LoggerClass):
    """
    Async Qdrant client for DocForge hybrid vector operations.

    Responsibilities:
    1. ``connect()`` — initialise the AsyncQdrantClient; call once at startup.
    2. ``ensure_collection()`` — create the collection with hybrid vector config if absent.
    3. ``upsert_chunks()`` — hybrid upsert (dense + sparse) of pre-embedded chunks.
    4. ``close()`` — release the client connection.

    Qdrant is an index — its contents are fully regenerable from Postgres + the embedding
    model.  Never treat it as a source of truth.
    """

    def __init__(
        self,
        host: str,
        port: int = 6333,
        api_key: str | None = None,
        https: bool = False,
    ) -> None:
        """
        Initialize the Qdrant client configuration.

        Args:
            host (str): Qdrant server hostname.
            port (int): Qdrant REST/gRPC port (default 6333).
            api_key (str | None): Optional API key for authenticated clusters.
            https (bool): Use HTTPS when True (for Qdrant Cloud).
        """
        LoggerClass.__init__(self)
        self._host = host
        self._port = port
        self._api_key = api_key
        self._https = https
        self._client: AsyncQdrantClient | None = None

    async def connect(self) -> None:
        """
        Initialize the AsyncQdrantClient.

        Raises:
            RuntimeError: If already connected.
        """
        if self._client is not None:
            raise RuntimeError(f"QdrantStorageClient is already connected.")
        self._client = AsyncQdrantClient(
            host=self._host,
            port=self._port,
            api_key=self._api_key,
            https=self._https,
        )
        self.logger.info(
            f"QdrantStorageClient initialized → "
            f"{'https' if self._https else 'http'}://{self._host}:{self._port}"
        )

    async def close(self) -> None:
        """Release the Qdrant client."""
        if self._client is not None:
            await self._client.close()
            self._client = None
        self.logger.info(f"QdrantStorageClient disconnected.")

    async def ensure_collection(
        self,
        collection_name: str,
        dense_dim: int = BGE_M3_DIMENSION,
        field_dense_names: list[str] | None = None,
        field_sparse_names: list[str] | None = None,
        recreate: bool = False,
    ) -> None:
        """
        Create the Qdrant collection if it does not already exist.

        Configured for multi-field hybrid search (spec §7.2):
        - ``content_dense`` / ``content_bm25`` — always present (the chunk body).
        - one named dense vector per ``semantic`` metadata field (``meta_<field>_dense``).
        - one named sparse vector per ``lexical`` metadata field (``meta_<field>_bm25``).

        Qdrant fixes the vector schema at creation — changing the metadata schema requires a
        new pipeline_version + reindex (recreate=True), consistent with ADR-15.

        Args:
            collection_name (str): Target Qdrant collection name.
            dense_dim (int): Dense vector dimension (1024 for BGE-M3).
            field_dense_names (list[str] | None): Per-field dense vector names to create.
            field_sparse_names (list[str] | None): Per-field sparse vector names to create.
            recreate (bool): Drop and recreate if the collection already exists.

        Raises:
            RuntimeError: If not connected.
        """
        client = self._require_client()

        # 1. Optionally drop existing collection
        if recreate and await client.collection_exists(collection_name):
            await client.delete_collection(collection_name)
            self.logger.info(f"Qdrant: dropped collection {collection_name!r} for recreation.")

        # 2. Create collection if absent — content vectors + one per metadata field
        if not await client.collection_exists(collection_name):
            vectors_config = {
                DENSE_VECTOR_NAME: VectorParams(size=dense_dim, distance=Distance.COSINE, on_disk=True),
            }
            for vname in field_dense_names or []:
                vectors_config[vname] = VectorParams(size=dense_dim, distance=Distance.COSINE, on_disk=True)

            sparse_config = {SPARSE_VECTOR_NAME: SparseVectorParams()}
            for vname in field_sparse_names or []:
                sparse_config[vname] = SparseVectorParams()

            await client.create_collection(
                collection_name=collection_name,
                vectors_config=vectors_config,
                sparse_vectors_config=sparse_config,
            )
            self.logger.info(
                f"Qdrant: created collection {collection_name!r} "
                f"(dense={len(vectors_config)} vectors, sparse={len(sparse_config)} vectors)"
            )
        else:
            self.logger.debug(f"Qdrant: collection {collection_name!r} already exists.")

    async def drop_collection(self, collection_name: str) -> bool:
        """
        Delete a Qdrant collection if it exists (idempotent).

        Args:
            collection_name (str): Target collection.

        Returns:
            bool: True if a collection was dropped, False if it did not exist.
        """
        client = self._require_client()
        if not await client.collection_exists(collection_name):
            return False
        await client.delete_collection(collection_name)
        self.logger.info(f"Qdrant: dropped collection {collection_name!r}")
        return True

    # ─── Targeted point updates (single-document metadata sync) ─────────────────

    async def delete_points(self, collection_name: str, point_ids: list[str]) -> int:
        """
        Delete specific points by id (idempotent; missing ids are ignored by Qdrant).

        Args:
            collection_name (str): Target collection.
            point_ids (list[str]): Point ids (chunk ids) to delete.

        Returns:
            int: Number of point ids submitted for deletion.
        """
        if not point_ids:
            return 0
        client = self._require_client()
        if not await client.collection_exists(collection_name):
            return 0
        await client.delete(collection_name=collection_name, points_selector=PointIdsList(points=point_ids))
        self.logger.debug(f"Qdrant: deleted {len(point_ids)} point(s) → {collection_name!r}")
        return len(point_ids)

    async def set_points_payload(
        self, collection_name: str, point_ids: list[str], payload: dict[str, Any]
    ) -> None:
        """Merge a payload patch into the given points (existing keys overwritten)."""
        if not point_ids or not payload:
            return
        client = self._require_client()
        await client.set_payload(collection_name=collection_name, payload=payload, points=point_ids)
        self.logger.debug(f"Qdrant: set payload {list(payload)} on {len(point_ids)} point(s)")

    async def delete_points_payload_keys(
        self, collection_name: str, point_ids: list[str], keys: list[str]
    ) -> None:
        """Remove specific payload keys from the given points (for cleared metadata fields)."""
        if not point_ids or not keys:
            return
        client = self._require_client()
        await client.delete_payload(collection_name=collection_name, keys=keys, points=point_ids)
        self.logger.debug(f"Qdrant: removed payload keys {keys} from {len(point_ids)} point(s)")

    async def update_points_named_vector(
        self,
        collection_name: str,
        point_ids: list[str],
        vector_name: str,
        *,
        dense: list[float] | None = None,
        sparse: dict[int, float] | None = None,
    ) -> None:
        """
        Set one named vector to the same value on every given point.

        Document-level metadata fields embed to the same vector for all of a document's chunks,
        so a single embedding is broadcast across its points.

        Args:
            collection_name (str): Target collection.
            point_ids (list[str]): Points to update.
            vector_name (str): Named vector key (e.g. ``meta_dossier_dense``).
            dense (list[float] | None): Dense vector value, or None.
            sparse (dict[int, float] | None): Sparse BM25 map, or None.
        """
        if not point_ids or (dense is None and not sparse):
            return
        value: Any = dense if dense is not None else SparseVector(
            indices=list(sparse.keys()), values=list(sparse.values())
        )
        client = self._require_client()
        await client.update_vectors(
            collection_name=collection_name,
            points=[PointVectors(id=pid, vector={vector_name: value}) for pid in point_ids],
        )
        self.logger.debug(f"Qdrant: updated vector {vector_name!r} on {len(point_ids)} point(s)")

    async def delete_points_named_vectors(
        self, collection_name: str, point_ids: list[str], vector_names: list[str]
    ) -> None:
        """Delete named vectors from the given points (for cleared searchable fields)."""
        if not point_ids or not vector_names:
            return
        client = self._require_client()
        await client.delete_vectors(
            collection_name=collection_name, vectors=vector_names, points=point_ids
        )
        self.logger.debug(f"Qdrant: deleted vectors {vector_names} from {len(point_ids)} point(s)")

    async def upsert_points(
        self,
        collection_name: str,
        chunk_ids: list[str],
        dense_by_vector: dict[str, list[list[float] | None]],
        sparse_by_vector: dict[str, list[dict[int, float] | None]],
        payloads: list[dict[str, Any]],
    ) -> int:
        """
        Upsert points carrying multiple named dense + sparse vectors (spec §7.2).

        Idempotent by chunk_id. Per chunk, only vectors with a non-None value are attached —
        a chunk lacking a value for a field (e.g. an empty custom field) simply omits that
        named vector, which Qdrant supports.

        Args:
            collection_name (str): Target collection.
            chunk_ids (list[str]): UUID strings used as point IDs.
            dense_by_vector (dict): vector_name → list of dense vectors (one per chunk; None to skip).
            sparse_by_vector (dict): vector_name → list of BM25 maps (one per chunk; None to skip).
            payloads (list[dict]): Filterable payload per chunk.

        Returns:
            int: Number of points upserted.
        """
        if not chunk_ids:
            return 0
        n = len(chunk_ids)
        client = self._require_client()

        points: list[PointStruct] = []
        for i, chunk_id in enumerate(chunk_ids):
            vector: dict[str, Any] = {}
            # 1. Dense named vectors (content + per semantic field)
            for vname, vecs in dense_by_vector.items():
                v = vecs[i] if i < len(vecs) else None
                if v is not None:
                    vector[vname] = v
            # 2. Sparse named vectors (content + per lexical field)
            for vname, maps in sparse_by_vector.items():
                sp = maps[i] if i < len(maps) else None
                if sp:
                    vector[vname] = SparseVector(indices=list(sp.keys()), values=list(sp.values()))
            points.append(PointStruct(id=chunk_id, vector=vector, payload=payloads[i]))

        await client.upsert(collection_name=collection_name, points=points)
        self.logger.debug(f"Qdrant: upserted {n} multi-vector point(s) → {collection_name!r}")
        return n

    async def multi_search(
        self,
        collection_name: str,
        dense_query: list[float],
        sparse_query: dict[int, float] | None,
        dense_vectors: list[str],
        sparse_vectors: list[str],
        weights: dict[str, float],
        top_k: int = 10,
        payload_filter: dict | None = None,
    ) -> list[dict[str, Any]]:
        """
        Multi-field hybrid retrieval with weighted Reciprocal Rank Fusion (spec §9).

        The query is embedded once; it is compared against each enabled named vector
        (content + per-field dense/sparse). Each vector yields a ranked candidate list; the
        lists are fused client-side with per-vector weights (Qdrant's native RRF is unweighted).

        Args:
            collection_name (str): Target collection.
            dense_query (list[float]): Query dense embedding.
            sparse_query (dict[int, float] | None): Query BM25 sparse map.
            dense_vectors (list[str]): Dense named vectors to search (incl. content_dense).
            sparse_vectors (list[str]): Sparse named vectors to search (incl. content_bm25).
            weights (dict): vector_name → fusion weight.
            top_k (int): Number of fused results to return.
            payload_filter (dict | None): Raw Qdrant filter dict.

        Returns:
            list[dict]: ``id``, ``score`` (fused), ``payload`` for the top_k results.
        """
        # 1. Per-vector ranked candidate lists, fused with weighted RRF
        ranked = await self._ranked_lists(
            collection_name, dense_query, sparse_query, dense_vectors, sparse_vectors,
            payload_filter, max(top_k * 3, 20),
        )
        fused = FieldIndexHelpers.weighted_rrf(ranked, weights, top_k=top_k)
        if not fused:
            return []

        # 2. Fetch payloads for the winners in one retrieve call
        results = await self._hydrate_payloads(collection_name, fused)
        self.logger.debug(
            f"Qdrant weighted-RRF search → {collection_name!r} "
            f"vectors={len(ranked)} top_k={top_k} results={len(results)}"
        )
        return results

    async def multi_search_debug(
        self,
        collection_name: str,
        dense_query: list[float],
        sparse_query: dict[int, float] | None,
        dense_vectors: list[str],
        sparse_vectors: list[str],
        weights: dict[str, float],
        top_k: int = 10,
        payload_filter: dict | None = None,
    ) -> dict[str, Any]:
        """
        Like :meth:`multi_search`, but also exposes the fusion internals for debugging.

        Returns:
            dict: ``{"ranked": {vector → [ids]}, "fused": [{id, score}], "results": [...],
                "candidate_limit": int}`` — the per-vector ranked lists, the fused order, and
                the hydrated winners. Lets the UI explain *why* a chunk ranked where it did.
        """
        candidate_limit = max(top_k * 3, 20)
        ranked = await self._ranked_lists(
            collection_name, dense_query, sparse_query, dense_vectors, sparse_vectors,
            payload_filter, candidate_limit,
        )
        fused = FieldIndexHelpers.weighted_rrf(ranked, weights, top_k=top_k)
        results = await self._hydrate_payloads(collection_name, fused) if fused else []
        return {
            "ranked": ranked,
            "fused": [{"id": cid, "score": float(score)} for cid, score in fused],
            "results": results,
            "candidate_limit": candidate_limit,
        }

    # ─── Internal helpers ───────────────────────────────────────────────────────

    async def _ranked_lists(
        self,
        collection_name: str,
        dense_query: list[float],
        sparse_query: dict[int, float] | None,
        dense_vectors: list[str],
        sparse_vectors: list[str],
        payload_filter: dict | None,
        candidate_limit: int,
    ) -> dict[str, list[str]]:
        """Run one single-vector query per enabled named vector → {vector: [ranked ids]}."""
        client = self._require_client()
        qdrant_filter: Filter | None = Filter(**payload_filter) if payload_filter else None
        ranked: dict[str, list[str]] = {}

        # 1. Dense named vectors (content + per semantic field)
        for vname in dense_vectors:
            resp = await client.query_points(
                collection_name=collection_name, query=dense_query, using=vname,
                limit=candidate_limit, query_filter=qdrant_filter, with_payload=False,
            )
            ranked[vname] = [str(p.id) for p in resp.points]

        # 2. Sparse named vectors (content + per lexical field), only if a sparse query exists
        if sparse_query is not None:
            sp = SparseVector(indices=list(sparse_query.keys()), values=list(sparse_query.values()))
            for vname in sparse_vectors:
                resp = await client.query_points(
                    collection_name=collection_name, query=sp, using=vname,
                    limit=candidate_limit, query_filter=qdrant_filter, with_payload=False,
                )
                ranked[vname] = [str(p.id) for p in resp.points]
        return ranked

    async def _hydrate_payloads(
        self, collection_name: str, fused: list[tuple[str, float]]
    ) -> list[dict[str, Any]]:
        """Fetch payloads for the fused winners and shape them as result dicts."""
        client = self._require_client()
        ids = [cid for cid, _ in fused]
        records = await client.retrieve(collection_name=collection_name, ids=ids, with_payload=True)
        payload_by_id = {str(r.id): (dict(r.payload) if r.payload else {}) for r in records}
        return [{"id": cid, "score": float(score), "payload": payload_by_id.get(cid, {})}
                for cid, score in fused]

    def _require_client(self) -> AsyncQdrantClient:
        """Return the client, raising if not connected."""
        if self._client is None:
            raise RuntimeError(f"QdrantStorageClient is not connected.")
        return self._client
