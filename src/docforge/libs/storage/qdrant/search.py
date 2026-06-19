# ====== Code Summary ======
# Static helpers for Qdrant hybrid search: per-vector ranked-list retrieval,
# payload hydration, and result shaping for multi-field weighted-RRF fusion.

# ====== Standard Library Imports ======
from __future__ import annotations

from typing import Any

# ====== Third-Party Library Imports ======
from loggerplusplus import loggerplusplus
from qdrant_client import AsyncQdrantClient
from qdrant_client.models import Filter, SparseVector

# ====== Internal Project Imports ======
from libs.search.field_index import FieldIndexHelpers


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
    ) -> dict[str, list[str]]:
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

        Returns:
            dict[str, list[str]]: ``{vector_name: [ranked point ids]}`` for every queried vector.
        """
        qdrant_filter: Filter | None = Filter(**payload_filter) if payload_filter else None
        ranked: dict[str, list[str]] = {}
        cls.logger.debug(
            f"QdrantSearch: querying {len(dense_vectors)} dense + {len(sparse_vectors)} sparse vectors "
            f"(candidate_limit={candidate_limit}) on {collection_name!r}"
        )

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
            fused (list[tuple[str, float]]): Ordered ``(point_id, score)`` pairs from RRF fusion.

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
    ) -> dict[str, Any]:
        """
        Run the full multi-field weighted-RRF search and expose the fusion internals.

        Drives the shared pipeline used by both the plain and debug search entry points:
        per-vector ranked candidate lists → weighted RRF fusion → payload hydration.

        Args:
            client (AsyncQdrantClient): Live Qdrant client.
            collection_name (str): Target Qdrant collection.
            dense_query (list[float]): Query dense embedding.
            sparse_query (dict[int, float] | None): Query BM25 sparse map.
            dense_vectors (list[str]): Dense named vectors to search (incl. content_dense).
            sparse_vectors (list[str]): Sparse named vectors to search (incl. content_bm25).
            weights (dict[str, float]): vector_name → fusion weight.
            top_k (int): Number of fused results to return.
            payload_filter (dict | None): Raw Qdrant filter dict.

        Returns:
            dict[str, Any]: ``{"ranked": {vector → [ids]}, "fused": [(id, score)],
                "results": [{id, score, payload}], "candidate_limit": int}``.
        """
        candidate_limit = max(top_k * 3, 20)

        # 1. Per-vector ranked candidate lists
        ranked = await cls.ranked_lists(
            client=client,
            collection_name=collection_name,
            dense_query=dense_query,
            sparse_query=sparse_query,
            dense_vectors=dense_vectors,
            sparse_vectors=sparse_vectors,
            payload_filter=payload_filter,
            candidate_limit=candidate_limit,
        )

        # 2. Weighted RRF fusion across all ranked lists
        fused = FieldIndexHelpers.weighted_rrf(ranked, weights, top_k=top_k)

        # 3. Hydrate payloads for the fused winners (empty fused → no hydration)
        results = (
            await cls.hydrate_payloads(client, collection_name, fused) if fused else []
        )

        return {
            "ranked": ranked,
            "fused": fused,
            "results": results,
            "candidate_limit": candidate_limit,
        }
