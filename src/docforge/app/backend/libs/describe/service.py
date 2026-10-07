# ====== Code Summary ======
# CollectionDescriber — composes the lean agent guide of one collection (GET /collections/{id}/describe):
# identity + document count + title field, every metadata field with its meaning and real example
# values, the valid `search_in` targets, the filter grammar and example search bodies. READ-ONLY and
# bounded (one count + per-field bounded value reads); carries no pipeline/search blob and no secret.
# Composed guides are cached per collection (DescribeCache) behind the collection's change stamp.

# ====== Standard Library Imports ======
import uuid

# ====== Third-Party Library Imports ======
from loggerplusplus import LoggerClass

# ====== Internal Project Imports ======
from shared_libs.services.db import Database

# ====== Local Project Imports ======
from .cache import DESCRIBE_CACHE, DescribeCache
from .example_requests import ExampleRequestBuilder
from .field_guide_builder import FieldGuideBuilder
from .models import CollectionDescription
from .search_guide import SearchGuide

# How hits locate a page — the field to cite vs the one to draw with.
PAGE_NUMBERING_NOTE = "Hits carry page (0-based, for drawing) and page_number (1-based, cite this)."


class CollectionDescriber(LoggerClass):
    """Compose a collection's agent-oriented guide from its contract + bounded value reads."""

    def __init__(self, database: Database, cache: DescribeCache = DESCRIBE_CACHE) -> None:
        """
        Args:
            database (Database): The shared data facade (collections, documents, metadata values).
            cache (DescribeCache): The guide cache (the process-wide instance by default).
        """
        LoggerClass.__init__(self)
        self._database = database
        self._cache = cache
        self._fields = FieldGuideBuilder(database.metadata_values)

    async def describe(self, collection_id: uuid.UUID) -> CollectionDescription | None:
        """
        Describe one collection for a client about to search it.

        Args:
            collection_id (uuid.UUID): The collection to describe.

        Returns:
            CollectionDescription | None: The guide, or None when the collection does not exist.
        """
        # 1. The change stamp first: None = unknown collection (the route 404s). Read BEFORE any
        #    value so a write racing the compose moves the stamp and the entry is refreshed next call.
        stamp = await self._database.collections.change_stamp(collection_id)
        if stamp is None:
            return None
        cached = self._cache.get(collection_id, stamp)
        if cached is not None:
            return cached

        # 2. Miss → read the collection, its schema + document count, and compose.
        collection = await self._database.collections.get(collection_id)
        if collection is None:
            return None
        schema = await self._database.collections.get_schema(collection_id)
        document_count = await self._database.documents.count_for_collection(collection_id)

        # 3. Describe every field (bounded value reads per field).
        fields = [await self._fields.build(field) for field in schema]
        self.logger.debug(
            f"Described collection {collection_id}: {len(fields)} field(s), {document_count} doc(s)"
        )

        # 4. Assemble the guide from the described fields, then cache it under the stamp read first.
        description = CollectionDescription(
            collection_id=collection.id,
            name=collection.name,
            document_count=document_count,
            title_field=collection.title_field,
            page_numbering=PAGE_NUMBERING_NOTE,
            fields=fields,
            searchable_targets=SearchGuide.targets(fields),
            filter_grammar=SearchGuide.filter_grammar(),
            example_requests=ExampleRequestBuilder.build(fields),
        )
        self._cache.put(collection_id, stamp, description)
        return description


__all__ = ["CollectionDescriber"]
