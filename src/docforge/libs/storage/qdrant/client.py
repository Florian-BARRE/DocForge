# ====== Code Summary ======
# Async Qdrant client wrapper for DocForge hybrid vector store operations.
# Manages connection lifecycle and delegates all operations to typed helper classes.
# Qdrant is the retrieval index — never the source of truth (that's Postgres).

# ====== Standard Library Imports ======
from __future__ import annotations

from typing import Any

# ====== Third-Party Library Imports ======
from loggerplusplus import LoggerClass
from qdrant_client import AsyncQdrantClient

# ====== Internal Project Imports ======
from libs.search.field_index import CONTENT_DENSE, CONTENT_SPARSE, RetrievalTuning

# ====== Local Project Imports ======
from .collection_admin import QdrantCollectionAdmin
from .payload import QdrantPointHelpers
from .search import QdrantSearchHelpers
from .upsert import QdrantUpsertHelpers

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

    All collection, point, and search operations are delegated to:
    - :class:`QdrantCollectionAdmin` — collection lifecycle helpers.
    - :class:`QdrantPointHelpers` — point / payload mutation helpers.
    - :class:`QdrantSearchHelpers` — ranked-list retrieval and payload hydration.

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

    # ─── Connection lifecycle ────────────────────────────────────────────────

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

    # ─── Collection lifecycle ────────────────────────────────────────────────

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
        await QdrantCollectionAdmin.ensure_collection(
            client=self._require_client(),
            collection_name=collection_name,
            dense_dim=dense_dim,
            field_dense_names=field_dense_names,
            field_sparse_names=field_sparse_names,
            recreate=recreate,
        )

    async def drop_collection(self, collection_name: str) -> bool:
        """
        Delete a Qdrant collection if it exists (idempotent).

        Args:
            collection_name (str): Target collection.

        Returns:
            bool: True if a collection was dropped, False if it did not exist.
        """
        return await QdrantCollectionAdmin.drop_collection(
            client=self._require_client(),
            collection_name=collection_name,
        )

    # ─── Targeted point updates (single-document metadata sync) ─────────────

    async def delete_points(self, collection_name: str, point_ids: list[str]) -> int:
        """
        Delete specific points by id (idempotent; missing ids are ignored by Qdrant).

        Args:
            collection_name (str): Target collection.
            point_ids (list[str]): Point ids (chunk ids) to delete.

        Returns:
            int: Number of point ids submitted for deletion.
        """
        return await QdrantPointHelpers.delete_points(
            client=self._require_client(),
            collection_name=collection_name,
            point_ids=point_ids,
        )

    async def set_points_payload(
        self, collection_name: str, point_ids: list[str], payload: dict[str, Any]
    ) -> None:
        """Merge a payload patch into the given points (existing keys overwritten)."""
        await QdrantPointHelpers.set_points_payload(
            client=self._require_client(),
            collection_name=collection_name,
            point_ids=point_ids,
            payload=payload,
        )

    async def delete_points_payload_keys(
        self, collection_name: str, point_ids: list[str], keys: list[str]
    ) -> None:
        """Remove specific payload keys from the given points (for cleared metadata fields)."""
        await QdrantPointHelpers.delete_points_payload_keys(
            client=self._require_client(),
            collection_name=collection_name,
            point_ids=point_ids,
            keys=keys,
        )

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
        await QdrantPointHelpers.update_points_named_vector(
            client=self._require_client(),
            collection_name=collection_name,
            point_ids=point_ids,
            vector_name=vector_name,
            dense=dense,
            sparse=sparse,
        )

    async def delete_points_named_vectors(
        self, collection_name: str, point_ids: list[str], vector_names: list[str]
    ) -> None:
        """Delete named vectors from the given points (for cleared searchable fields)."""
        await QdrantPointHelpers.delete_points_named_vectors(
            client=self._require_client(),
            collection_name=collection_name,
            point_ids=point_ids,
            vector_names=vector_names,
        )

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
        return await QdrantUpsertHelpers.upsert_points(
            client=self._require_client(),
            collection_name=collection_name,
            chunk_ids=chunk_ids,
            dense_by_vector=dense_by_vector,
            sparse_by_vector=sparse_by_vector,
            payloads=payloads,
        )

    # ─── Hybrid search ───────────────────────────────────────────────────────

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
        tuning: RetrievalTuning | None = None,
    ) -> list[dict[str, Any]]:
        """
        Multi-field hybrid retrieval with configurable fusion (spec §9).

        The query is embedded once; it is compared against each enabled named vector
        (content + per-field dense/sparse). Each vector yields a ranked candidate list; the
        lists are fused client-side per ``tuning`` (weighted RRF or DBSF) with per-vector
        weights, so arbitrary multi-field weighting is preserved.

        Args:
            collection_name (str): Target collection.
            dense_query (list[float]): Query dense embedding.
            sparse_query (dict[int, float] | None): Query BM25 sparse map.
            dense_vectors (list[str]): Dense named vectors to search (incl. content_dense).
            sparse_vectors (list[str]): Sparse named vectors to search (incl. content_bm25).
            weights (dict): vector_name → fusion weight.
            top_k (int): Number of fused results to return.
            payload_filter (dict | None): Raw Qdrant filter dict.
            tuning (RetrievalTuning | None): Fusion / candidate sizing / threshold tuning.

        Returns:
            list[dict]: ``id``, ``score`` (fused), ``payload`` for the top_k results.
        """
        # 1. Run the shared search pipeline (ranked lists → fusion → hydration)
        outcome = await QdrantSearchHelpers.run_multi_search(
            client=self._require_client(),
            collection_name=collection_name,
            dense_query=dense_query,
            sparse_query=sparse_query,
            dense_vectors=dense_vectors,
            sparse_vectors=sparse_vectors,
            weights=weights,
            top_k=top_k,
            payload_filter=payload_filter,
            tuning=tuning,
        )

        # 2. Return only the hydrated, rank-ordered results
        results = outcome["results"]
        self.logger.debug(
            f"Qdrant {(tuning or RetrievalTuning()).fusion} search → {collection_name!r} "
            f"vectors={len(outcome['ranked'])} top_k={top_k} results={len(results)}"
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
        tuning: RetrievalTuning | None = None,
    ) -> dict[str, Any]:
        """
        Like :meth:`multi_search`, but also exposes the fusion internals for debugging.

        Returns:
            dict: ``{"ranked": {vector → [ids]}, "fused": [{id, score}], "results": [...],
                "candidate_limit": int}`` — the per-vector ranked lists, the fused order, and
                the hydrated winners. Lets the UI explain *why* a chunk ranked where it did.
        """
        # 1. Run the shared search pipeline (ranked lists → fusion → hydration)
        outcome = await QdrantSearchHelpers.run_multi_search(
            client=self._require_client(),
            collection_name=collection_name,
            dense_query=dense_query,
            sparse_query=sparse_query,
            dense_vectors=dense_vectors,
            sparse_vectors=sparse_vectors,
            weights=weights,
            top_k=top_k,
            payload_filter=payload_filter,
            tuning=tuning,
        )

        # 2. Reshape the fused pairs into JSON-friendly dicts for the debug view
        return {
            "ranked": outcome["ranked"],
            "fused": [{"id": cid, "score": float(score)} for cid, score in outcome["fused"]],
            "results": outcome["results"],
            "candidate_limit": outcome["candidate_limit"],
        }

    # ─── Internal ───────────────────────────────────────────────────────────

    def _require_client(self) -> AsyncQdrantClient:
        """Return the client, raising if not connected."""
        if self._client is None:
            raise RuntimeError(f"QdrantStorageClient is not connected.")
        return self._client
