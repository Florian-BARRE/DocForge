# ====== Code Summary ======
# Static helpers for Qdrant hybrid search: per-vector ranked-list retrieval
# (ids + raw scores), payload hydration, and result shaping for multi-field
# fusion (weighted RRF or distribution-based score fusion / DBSF).
# All tuning (candidate sizing, fusion method, rrf_k, score threshold) is driven
# by the RetrievalTuning object — no constant is hard-coded here.

# ====== Standard Library Imports ======
from __future__ import annotations

from typing import Any

# ====== Third-Party Library Imports ======
from loggerplusplus import loggerplusplus
from qdrant_client import AsyncQdrantClient
from qdrant_client.models import Filter, SparseVector

# ====== Internal Project Imports ======
from libs.search.field_index import FieldIndexHelpers, RetrievalTuning


class QdrantSearchHelpers:
    """
    Static helpers for Qdrant multi-field hybrid search operations.

    Encapsulates per-vector query execution, payload hydration, and result
    shaping.  All methods take the live ``AsyncQdrantClient`` as an explicit
    argument so that this class carries no instance state of its own.
    """

    logger = loggerplusplus.bind(identifier="QdrantSearchHelpers")

    def __new__(cls, *args: object, **kwargs: object) -> None:  # type: ignore[return]
        """Block instantiation — this is a static-only class."""
        raise TypeError("QdrantSearchHelpers is a static-only class and cannot be instantiated.")

    @classmethod
    async def ranked_lists(
        cls,
        client: AsyncQdrantClient,
        collection_name: str,
        dense_query: list[float],
        sparse_query: dict[int, float] | None,
        dense_vectors: list[str],
        sparse_vectors: list[str],
        payload_filter: dict | None,
        candidate_limit: int,
        score_threshold: float | None = None,
    ) -> dict[str, list[tuple[str, float]]]:
        """
        Run one single-vector query per enabled named vector.

        Args:
            client (AsyncQdrantClient): Live Qdrant client.
            collection_name (str): Target Qdrant collection.
            dense_query (list[float]): Query dense embedding.
            sparse_query (dict[int, float] | None): Query BM25 sparse map.
            dense_vectors (list[str]): Dense named vectors to query.
            sparse_vectors (list[str]): Sparse named vectors to query.
            payload_filter (dict | None): Raw Qdrant filter dict.
            candidate_limit (int): Maximum candidates per vector.
            score_threshold (float | None): Per-vector minimum similarity; None disables.

        Returns:
            dict[str, list[tuple[str, float]]]: ``{vector_name: [(point_id, score), ...]}``
                for every queried vector, ordered best-first.
        """
        qdrant_filter: Filter | None = Filter(**payload_filter) if payload_filter else None
        ranked: dict[str, list[tuple[str, float]]] = {}
        cls.logger.debug(
            f"QdrantSearch: querying {len(dense_vectors)} dense + {len(sparse_vectors)} sparse vectors "
            f"(candidate_limit={candidate_limit}, score_threshold={score_threshold}) on {collection_name!r}"
        )

        # 1. Dense named vectors (content + per semantic field)
        for vname in dense_vectors:
            resp = await client.query_points(
                collection_name=collection_name, query=dense_query, using=vname,
                limit=candidate_limit, query_filter=qdrant_filter, with_payload=False,
                score_threshold=score_threshold,
            )
            ranked[vname] = [(str(p.id), float(p.score)) for p in resp.points]

        # 2. Sparse named vectors (content + per lexical field), only if a sparse query exists
        if sparse_query is not None:
            sp = SparseVector(indices=list(sparse_query.keys()), values=list(sparse_query.values()))
            for vname in sparse_vectors:
                resp = await client.query_points(
                    collection_name=collection_name, query=sp, using=vname,
                    limit=candidate_limit, query_filter=qdrant_filter, with_payload=False,
                    score_threshold=score_threshold,
                )
                ranked[vname] = [(str(p.id), float(p.score)) for p in resp.points]

        return ranked

    @classmethod
    async def hydrate_payloads(
        cls,
        client: AsyncQdrantClient,
        collection_name: str,
        fused: list[tuple[str, float]],
    ) -> list[dict[str, Any]]:
        """
        Fetch payloads for the fused winners and shape them as result dicts.

        Args:
            client (AsyncQdrantClient): Live Qdrant client.
            collection_name (str): Target Qdrant collection.
            fused (list[tuple[str, float]]): Ordered ``(point_id, score)`` pairs from fusion.

        Returns:
            list[dict]: ``{"id": str, "score": float, "payload": dict}`` for each fused winner.
        """
        # 1. Batch-retrieve payloads for all winners in one round-trip
        ids = [cid for cid, _ in fused]
        cls.logger.debug(f"QdrantSearch: hydrating {len(ids)} fused winner(s) from {collection_name!r}")
        records = await client.retrieve(collection_name=collection_name, ids=ids, with_payload=True)
        payload_by_id = {str(r.id): (dict(r.payload) if r.payload else {}) for r in records}

        # 2. Build result dicts preserving fused rank order and scores
        return [
            {"id": cid, "score": float(score), "payload": payload_by_id.get(cid, {})}
            for cid, score in fused
        ]

    @classmethod
    async def fetch_vectors(
        cls,
        client: AsyncQdrantClient,
        collection_name: str,
        ids: list[str],
        vector_name: str,
    ) -> dict[str, list[float]]:
        """
        Fetch one named dense vector for a set of points (used by MMR diversity).

        Args:
            client (AsyncQdrantClient): Live Qdrant client.
            collection_name (str): Target Qdrant collection.
            ids (list[str]): Point ids whose vectors to retrieve.
            vector_name (str): Named dense vector to pull (e.g. ``content_dense``).

        Returns:
            dict[str, list[float]]: ``{point_id: vector}`` — points lacking the vector are omitted.
        """
        if not ids:
            return {}
        records = await client.retrieve(
            collection_name=collection_name, ids=ids,
            with_payload=False, with_vectors=[vector_name],
        )
        out: dict[str, list[float]] = {}
        for r in records:
            vec = (r.vector or {}).get(vector_name) if isinstance(r.vector, dict) else None
            if vec:
                out[str(r.id)] = list(vec)
        return out

    @classmethod
    def _fuse(
        cls,
        scored_lists: dict[str, list[tuple[str, float]]],
        weights: dict[str, float],
        top_k: int,
        tuning: RetrievalTuning,
    ) -> list[tuple[str, float]]:
        """
        Fuse per-vector scored lists into one ranking using the configured method.

        Args:
            scored_lists (dict): vector_name → ``[(id, score), ...]``.
            weights (dict): vector_name → fusion weight.
            top_k (int): Number of fused results to return.
            tuning (RetrievalTuning): Fusion method + rrf_k.

        Returns:
            list[tuple[str, float]]: ``(id, fused_score)`` ordered by descending score.
        """
        # DBSF works on raw scores; RRF works on rank positions only.
        if tuning.fusion == "dbsf":
            return FieldIndexHelpers.dbsf_fuse(scored_lists, weights, top_k=top_k)
        ranked_ids = {v: [cid for cid, _ in items] for v, items in scored_lists.items()}
        return FieldIndexHelpers.weighted_rrf(ranked_ids, weights, top_k=top_k, rrf_k=tuning.rrf_k)

    @classmethod
    async def run_multi_search(
        cls,
        client: AsyncQdrantClient,
        collection_name: str,
        dense_query: list[float],
        sparse_query: dict[int, float] | None,
        dense_vectors: list[str],
        sparse_vectors: list[str],
        weights: dict[str, float],
        top_k: int,
        payload_filter: dict | None,
        tuning: RetrievalTuning | None = None,
    ) -> dict[str, Any]:
        """
        Run the full multi-field fusion search and expose the fusion internals.

        Drives the shared pipeline used by both the plain and debug search entry points:
        per-vector ranked candidate lists → configured fusion → payload hydration.

        Args:
            client (AsyncQdrantClient): Live Qdrant client.
            collection_name (str): Target Qdrant collection.
            dense_query (list[float]): Query dense embedding.
            sparse_query (dict[int, float] | None): Query BM25 sparse map.
            dense_vectors (list[str]): Dense named vectors to search.
            sparse_vectors (list[str]): Sparse named vectors to search.
            weights (dict[str, float]): vector_name → fusion weight.
            top_k (int): Number of fused results to return.
            payload_filter (dict | None): Raw Qdrant filter dict.
            tuning (RetrievalTuning | None): Candidate sizing, fusion method, rrf_k,
                score threshold; defaults reproduce the historical behavior.

        Returns:
            dict[str, Any]: ``{"ranked": {vector → [ids]}, "fused": [(id, score)],
                "results": [{id, score, payload}], "candidate_limit": int}``.
        """
        tuning = tuning or RetrievalTuning()
        candidate_limit = tuning.candidate_limit(top_k)

        # 1. Per-vector ranked candidate lists (ids + raw scores)
        scored = await cls.ranked_lists(
            client=client,
            collection_name=collection_name,
            dense_query=dense_query,
            sparse_query=sparse_query,
            dense_vectors=dense_vectors,
            sparse_vectors=sparse_vectors,
            payload_filter=payload_filter,
            candidate_limit=candidate_limit,
            score_threshold=tuning.score_threshold,
        )

        # 2. Fuse across all ranked lists with the configured method (RRF or DBSF)
        fused = cls._fuse(scored, weights, top_k=top_k, tuning=tuning)

        # 3. Hydrate payloads for the fused winners (empty fused → no hydration)
        results = (
            await cls.hydrate_payloads(client, collection_name, fused) if fused else []
        )

        # 4. ids-only ranked view for the debug per-vector rank breakdown
        ranked_ids = {v: [cid for cid, _ in items] for v, items in scored.items()}

        return {
            "ranked": ranked_ids,
            "fused": fused,
            "results": results,
            "candidate_limit": candidate_limit,
        }
