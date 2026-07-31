# ====== Code Summary ======
# QdrantSearchApi — the READ operation of the vector store: a hybrid, FILTERED search over the named
# vectors. Each queried vector is a prefetch branch; the filter (on the filterable payload fields) is
# applied to every branch so only matching points are ranked; Qdrant fuses the branches server-side
# with Reciprocal Rank Fusion and returns the winning (chunk_id, score) to hydrate from Postgres.

# ====== Standard Library Imports ======
from collections.abc import Sequence

# ====== Third-Party Library Imports ======
from qdrant_client import AsyncQdrantClient, models

# ====== Local Project Imports ======
from ..vectors import Condition, Match, MatchAny, SparseVec


class QdrantSearchApi:
    """Static read operation (hybrid filtered search) for the vector store."""

    def __new__(cls, *args: object, **kwargs: object) -> None:
        raise TypeError("QdrantSearchApi is a static-only class and cannot be instantiated.")

    @staticmethod
    def _to_field_condition(cond: Condition) -> models.FieldCondition:
        """Translate one clean condition into a qdrant FieldCondition."""
        if isinstance(cond, Match):
            return models.FieldCondition(key=cond.field, match=models.MatchValue(value=cond.value))
        if isinstance(cond, MatchAny):
            return models.FieldCondition(key=cond.field, match=models.MatchAny(any=cond.values))
        # Range — datetime bounds need qdrant's DatetimeRange; numeric bounds its Range.
        range_cls = models.DatetimeRange if cond.is_datetime else models.Range
        return models.FieldCondition(
            key=cond.field,
            range=range_cls(gte=cond.gte, lte=cond.lte, gt=cond.gt, lt=cond.lt),
        )

    @staticmethod
    def _to_filter(
        conditions: Sequence[Condition], exclusions: Sequence[Condition]
    ) -> models.Filter:
        """
        Translate the clean conditions into a qdrant Filter.

        ``conditions`` are ANDed under ``must`` (a point must match all of them); ``exclusions``
        go under ``must_not`` (a point matching any of them is dropped) — the mechanism the search
        facade uses to hide disabled points: the ``enabled==false`` chunk flag and the disabled
        documents' ids.
        """
        musts = [QdrantSearchApi._to_field_condition(cond) for cond in conditions]
        must_nots = [QdrantSearchApi._to_field_condition(cond) for cond in exclusions]
        return models.Filter(must=musts, must_not=must_nots)

    # qdrant-client's `query` params (Prefetch + query_points) are 25+-member Unions that PyCharm
    # truncates and mis-flags — FusionQuery / SparseVector ARE valid but sit past the truncation.
    # Suppress that one false positive for the whole (qdrant-only) method.
    # noinspection PyTypeChecker
    @staticmethod
    async def hybrid(
        client: AsyncQdrantClient,
        name: str,
        *,
        dense: dict[str, list[float]] | None = None,
        sparse: dict[str, SparseVec] | None = None,
        conditions: Sequence[Condition] = (),
        exclusions: Sequence[Condition] = (),
        limit: int = 10,
        prefetch_limit: int | None = None,
        fusion: str = "rrf",
    ) -> list[tuple[str, float]]:
        """
        Filtered hybrid search across the named vectors, fused with the chosen strategy.

        Single-stage: the dense/sparse branches over-sample per branch, then are fused server-side
        with the chosen strategy and the top ``limit`` returned. The payload filter lives on each
        branch, so a disabled chunk never enters the pool.

        Args:
            client (AsyncQdrantClient): The connection from QdrantClient.raw.
            name (str): The Qdrant collection name.
            dense (dict | None): vector name → query dense vector.
            sparse (dict | None): vector name → query sparse vector.
            conditions (Sequence[Condition]): Filters on the filterable payload fields (ANDed).
            exclusions (Sequence[Condition]): Filters whose matches are DROPPED (``must_not``) —
                the searchability exclusion set (the ``enabled==false`` chunk flag + disabled docs).
            limit (int): Number of fused results.
            prefetch_limit (int | None): Candidates fetched PER BRANCH before fusion; defaults to
                an over-sampling of the final limit (a branch pool of exactly `limit` starves RRF).
            fusion (str): How the dense/sparse branches are fused — ``"rrf"`` (Reciprocal Rank
                Fusion, rank-based, robust and score-scale-agnostic; the default) or ``"dbsf"``
                (Distribution-Based Score Fusion, which normalises each branch's score distribution
                before summing, letting a confident branch dominate — useful when one axis, e.g.
                exact lexical, should lead). Any other value falls back to RRF.

        Returns:
            list[tuple[str, float]]: (chunk_id, score), best first — hydrate from Postgres.
        """
        # 1. Build the payload filter (once) and apply it to every prefetch branch, each branch
        #    over-sampling so the fusion picks from a deep enough candidate pool.
        depth = prefetch_limit if prefetch_limit is not None else max(limit * 4, 100)
        query_filter = (
            QdrantSearchApi._to_filter(conditions, exclusions) if conditions or exclusions else None
        )
        fusion_strategy = models.Fusion.DBSF if fusion == "dbsf" else models.Fusion.RRF
        prefetch: list[models.Prefetch] = []
        for vec_name, vector in (dense or {}).items():
            prefetch.append(
                models.Prefetch(query=vector, using=vec_name, limit=depth, filter=query_filter)
            )
        for vec_name, sp in (sparse or {}).items():
            prefetch.append(
                models.Prefetch(
                    query=models.SparseVector(indices=sp.indices, values=sp.values),
                    using=vec_name,
                    limit=depth,
                    filter=query_filter,
                )
            )
        # 2. Fuse the branches server-side with the chosen strategy.
        response = await client.query_points(
            collection_name=name,
            prefetch=prefetch,
            query=models.FusionQuery(fusion=fusion_strategy),
            limit=limit,
            with_payload=False,
        )
        return [(str(point.id), point.score) for point in response.points]


__all__ = ["QdrantSearchApi"]
