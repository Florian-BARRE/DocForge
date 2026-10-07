# ====== Code Summary ======
# QdrantBrowseApi — the query-LESS read of the vector store: page through the points matching a
# payload filter in a deterministic (document_id, chunk_index, chunk_id) order. Qdrant's own scroll
# orders by point id (random chunk UUIDs), and ``order_by`` takes a single indexed numeric key, so the
# document-then-chunk order is assembled here: one exact FACET on the indexed document_id key gives
# the matching documents and their matching-point counts; documents are walked in id order and only as
# many as the page needs are scrolled (one filtered scroll per batch, payload = the two order keys),
# sorted, and cut after the keyset cursor. The filter is the SAME Condition translation the hybrid
# search uses (QdrantSearchApi._to_filter), so includes/excludes behave identically.

# ====== Standard Library Imports ======
from collections.abc import Sequence

# ====== Third-Party Library Imports ======
from loggerplusplus import loggerplusplus
from qdrant_client import AsyncQdrantClient

# ====== Local Project Imports ======
from ..vectors import CHUNK_INDEX_KEY, DOCUMENT_ID_KEY, Condition, MatchAny
from .search_api import QdrantSearchApi

# Upper bound on distinct documents one facet call enumerates — a browse over a collection with more
# matching documents than this would silently skip the overflow, so hitting it is logged loudly.
MAX_BROWSE_DOCUMENTS = 100_000

# Points fetched per scroll round-trip while collecting a batch of documents' matching chunks.
_SCROLL_PAGE = 512

# One browse key: (document_id, chunk_index, chunk_id) — the total order of a browse.
BrowseKey = tuple[str, int, str]


class QdrantBrowseApi:
    """Static, ordered, filter-only paging over a collection's points."""

    logger = loggerplusplus.bind(identifier="QdrantBrowseApi")

    def __new__(cls, *args: object, **kwargs: object) -> None:
        raise TypeError("QdrantBrowseApi is a static-only class and cannot be instantiated.")

    @classmethod
    async def __document_counts(
        cls, client: AsyncQdrantClient, name: str, conditions: list, exclusions: list
    ) -> list[tuple[str, int]]:
        """Every matching document id with its matching-point count, in document-id order."""
        # 1. An EXACT facet on the keyword-indexed document_id — the matching documents + counts.
        response = await client.facet(
            collection_name=name,
            key=DOCUMENT_ID_KEY,
            facet_filter=QdrantSearchApi._to_filter(conditions, exclusions),
            limit=MAX_BROWSE_DOCUMENTS,
            exact=True,
        )
        if len(response.hits) >= MAX_BROWSE_DOCUMENTS:
            cls.logger.warning(
                f"Browse of {name}: {len(response.hits)} matching documents reached the "
                f"{MAX_BROWSE_DOCUMENTS} cap — documents past it are not browsable"
            )
        return sorted((str(hit.value), hit.count) for hit in response.hits)

    @staticmethod
    async def __scroll_keys(
        client: AsyncQdrantClient,
        name: str,
        conditions: list,
        exclusions: list,
        document_ids: list[str],
    ) -> list[BrowseKey]:
        """Every matching point of the given documents as a browse key (unsorted)."""
        # 1. Same filter, narrowed to the batch's documents; only the two order keys are fetched.
        scoped = QdrantSearchApi._to_filter(
            [*conditions, MatchAny(field=DOCUMENT_ID_KEY, values=document_ids)], exclusions
        )
        keys: list[BrowseKey] = []
        offset = None
        while True:
            points, offset = await client.scroll(
                collection_name=name,
                scroll_filter=scoped,
                limit=_SCROLL_PAGE,
                offset=offset,
                with_payload=[DOCUMENT_ID_KEY, CHUNK_INDEX_KEY],
                with_vectors=False,
            )
            for point in points:
                payload = point.payload or {}
                keys.append(
                    (
                        str(payload.get(DOCUMENT_ID_KEY, "")),
                        int(payload.get(CHUNK_INDEX_KEY) or 0),
                        str(point.id),
                    )
                )
            # 2. Qdrant returns no next offset once the filtered set is exhausted.
            if offset is None:
                return keys

    @classmethod
    async def page(
        cls,
        client: AsyncQdrantClient,
        name: str,
        *,
        conditions: Sequence[Condition] = (),
        exclusions: Sequence[Condition] = (),
        after: BrowseKey | None = None,
        limit: int = 20,
    ) -> list[BrowseKey]:
        """
        Return up to ``limit`` matching points strictly after ``after``, in browse order.

        Args:
            client (AsyncQdrantClient): The connection from QdrantClient.raw.
            name (str): The Qdrant collection name.
            conditions (Sequence[Condition]): Filters every point must match (``must``).
            exclusions (Sequence[Condition]): Filters whose matches are dropped (``must_not``).
            after (BrowseKey | None): The keyset cursor — the last key of the previous page; None
                starts at the beginning.
            limit (int): The maximum number of keys to return.

        Returns:
            list[BrowseKey]: (document_id, chunk_index, chunk_id) keys, ascending.
        """
        # 1. The matching documents in id order, skipping those wholly before the cursor.
        must, must_not = list(conditions), list(exclusions)
        documents = await cls.__document_counts(client, name, must, must_not)
        if after is not None:
            documents = [entry for entry in documents if entry[0] >= after[0]]

        # 2. Walk the documents in batches sized by their counts until the page is full.
        collected: list[BrowseKey] = []
        position = 0
        while len(collected) < limit and position < len(documents):
            batch: list[str] = []
            budget = 0
            while position < len(documents) and (not batch or budget < limit - len(collected)):
                document_id, count = documents[position]
                batch.append(document_id)
                budget += count
                position += 1
            keys = sorted(await cls.__scroll_keys(client, name, must, must_not, batch))
            collected.extend(key for key in keys if after is None or key > after)
        return collected[:limit]


__all__ = ["QdrantBrowseApi", "BrowseKey", "MAX_BROWSE_DOCUMENTS"]
