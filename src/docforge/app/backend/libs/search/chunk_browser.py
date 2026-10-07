# ====== Code Summary ======
# ChunkBrowser — the query-less read behind POST /collections/{id}/chunks/browse: list a collection's
# chunks matching a (resolved) filter map, in (document, chunk_index) order, one keyset page at a time.
# The filter is translated by the SAME build_match_conditions the search read port uses, the page keys
# come from SearchFacade.browse_keys (the search's disabled-chunk/document exclusion baked in), and the
# page is hydrated by the search read port's own hydrate() — so a browsed chunk has exactly the shape
# (and projection-driven read skipping) of a search hit, minus the score.

# ====== Standard Library Imports ======
import uuid
from collections.abc import Collection
from dataclasses import dataclass

# ====== Third-Party Library Imports ======
from loggerplusplus import LoggerClass

# ====== Internal Project Imports ======
from config import RUNTIME_CONFIG
from shared_libs.public_models.search import Hit
from shared_libs.services.db import Database
from shared_libs.services.db.postgresql.tables import MetadataField
from shared_libs.services.db.qdrant import build_match_conditions

# ====== Local Project Imports ======
from .browse_cursor import BrowseCursor
from .hit_projection import HitProjection
from .read_port import CollectionReadPortImpl


@dataclass(frozen=True, slots=True)
class BrowsePage:
    """
    One browse page.

    Attributes:
        hits (list[Hit]): The page's hydrated chunks in browse order (score left at its default).
        next_cursor (BrowseCursor | None): Where the next page starts; None on the last page.
    """

    hits: list[Hit]
    next_cursor: BrowseCursor | None


class ChunkBrowser(LoggerClass):
    """Ordered, filter-only paging over a collection's searchable chunks."""

    def __init__(self, database: Database) -> None:
        """
        Args:
            database (Database): The shared data facade (search keys + the read port's hydration).
        """
        LoggerClass.__init__(self)
        self._database = database

    async def browse(
        self,
        collection_id: uuid.UUID,
        *,
        filters: dict | None,
        limit: int,
        cursor: BrowseCursor | None = None,
        text_fields: Collection[str] = frozenset(),
        title_field: MetadataField | None = None,
        projection: HitProjection | None = None,
    ) -> BrowsePage:
        """
        Return one page of the collection's chunks matching ``filters``, in browse order.

        Args:
            collection_id (uuid.UUID): The collection to browse.
            filters (dict | None): The resolved filter map (as the search graph would receive it).
            limit (int): The page size.
            cursor (BrowseCursor | None): The previous page's next_cursor; None = the first page.
            text_fields (Collection[str]): Filtered fields matched as full text.
            title_field (MetadataField | None): The collection's display-title field.
            projection (HitProjection | None): The requested fields (hydration skips the rest).

        Returns:
            BrowsePage: The hydrated page and the cursor of the next one.
        """
        # 1. One key past the page tells whether a next page exists without a second call.
        keys = await self._database.search.browse_keys(
            collection_id,
            conditions=build_match_conditions(filters or {}, frozenset(text_fields)),
            after=cursor.key() if cursor is not None else None,
            limit=limit + 1,
            max_disabled_exclusions=RUNTIME_CONFIG.SEARCH_MAX_DISABLED_DOC_EXCLUSIONS,
        )
        page = keys[:limit]
        next_cursor = BrowseCursor(*page[-1]) if len(keys) > limit else None

        # 2. Hydrate the page through the search read port (same hit shape + read skipping); a
        #    chunk whose row vanished meanwhile is dropped, the order is the browse order.
        read_port = CollectionReadPortImpl(
            self._database,
            collection_id,
            text_fields=text_fields,
            title_field=title_field,
            projection=projection,
        )
        hydrated = await read_port.hydrate([chunk_id for _, _, chunk_id in page])
        hits = [hydrated[chunk_id] for _, _, chunk_id in page if chunk_id in hydrated]
        self.logger.debug(
            f"Browse of {collection_id}: {len(hits)} chunk(s), more={next_cursor is not None}"
        )
        return BrowsePage(hits=hits, next_cursor=next_cursor)


__all__ = ["ChunkBrowser", "BrowsePage"]
