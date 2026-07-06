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
from ..vectors import Condition, Match, MatchAny, Range, SparseVec


class QdrantSearchApi:
    """Static read operation (hybrid filtered search) for the vector store."""

    def __new__(cls, *args: object, **kwargs: object) -> None:
        raise TypeError("QdrantSearchApi is a static-only class and cannot be instantiated.")

    @staticmethod
    def _to_filter(conditions: Sequence[Condition]) -> models.Filter:
        """Translate the clean conditions into a qdrant Filter (all ANDed under ``must``)."""
        musts: list[models.FieldCondition] = []
        for cond in conditions:
            if isinstance(cond, Match):
                musts.append(
                    models.FieldCondition(key=cond.field, match=models.MatchValue(value=cond.value))
                )
            elif isinstance(cond, MatchAny):
                musts.append(
                    models.FieldCondition(key=cond.field, match=models.MatchAny(any=cond.values))
                )
            elif isinstance(cond, Range):
                # Datetime bounds need qdrant's DatetimeRange; numeric bounds its Range.
                range_cls = models.DatetimeRange if cond.is_datetime else models.Range
                musts.append(
                    models.FieldCondition(
                        key=cond.field,
                        range=range_cls(gte=cond.gte, lte=cond.lte, gt=cond.gt, lt=cond.lt),
                    )
                )
        return models.Filter(must=musts)

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
        limit: int = 10,
        prefetch_limit: int | None = None,
    ) -> list[tuple[str, float]]:
        """
        Filtered hybrid search across the named vectors, fused with Reciprocal Rank Fusion.

        Args:
            client (AsyncQdrantClient): The connection from QdrantClient.raw.
            name (str): The Qdrant collection name.
            dense (dict | None): vector name → query dense vector.
            sparse (dict | None): vector name → query sparse vector.
            conditions (Sequence[Condition]): Filters on the filterable payload fields (ANDed).
            limit (int): Number of fused results.
            prefetch_limit (int | None): Candidates fetched PER BRANCH before fusion; defaults to
                an over-sampling of the final limit (a branch pool of exactly `limit` starves RRF).

        Returns:
            list[tuple[str, float]]: (chunk_id, fused score), best first — hydrate from Postgres.
        """
        # 1. Build the payload filter (once) and apply it to every prefetch branch, each branch
        #    over-sampling so the fusion picks from a deep enough candidate pool.
        depth = prefetch_limit if prefetch_limit is not None else max(limit * 4, 100)
        query_filter = QdrantSearchApi._to_filter(conditions) if conditions else None
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
        # 2. Fuse the branches server-side with RRF.
        response = await client.query_points(
            collection_name=name,
            prefetch=prefetch,
            query=models.FusionQuery(fusion=models.Fusion.RRF),
            limit=limit,
            with_payload=False,
        )
        return [(str(point.id), point.score) for point in response.points]


__all__ = ["QdrantSearchApi"]
