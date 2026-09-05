# ====== Code Summary ======
# DocumentSelectorResolver — turns the shared DocumentSelector into a concrete, collection-scoped set
# of document ids that every bulk op then acts on. Id mode validates that each id exists AND belongs
# to the collection (a foreign or unknown id fails the whole call — never a partial mutation across
# tenants). Filter mode resolves the filter to every matching id in the collection (via the
# index-friendly id projection) minus the deselected ``exclude_ids`` — the "select-all-100k-minus-3"
# the UI needs without ever shipping ids to the client. Raises a plain ValueError the router maps to
# a 422; the collection-existence (404) and scope (403) gates are the router's, run before this.

# ====== Standard Library Imports ======
import uuid
from collections.abc import Sequence

# ====== Third-Party Library Imports ======
from loggerplusplus import LoggerClass

# ====== Internal Project Imports ======
from shared_libs.services.db import Database
from shared_libs.services.db.postgresql.tables import MetadataField

# ====== Local Project Imports ======
from .mapper import CorpusMapper
from .models import DocumentSelector


class DocumentSelectorResolver(LoggerClass):
    """Resolve a DocumentSelector to the concrete, collection-scoped set of target document ids."""

    def __init__(self, database: Database) -> None:
        """
        Args:
            database (Database): The persistence façade (document reads + the filter id projection).
        """
        LoggerClass.__init__(self)
        self._database = database

    async def resolve(
        self,
        collection_id: uuid.UUID,
        selector: DocumentSelector,
        schema: Sequence[MetadataField],
        limit: int | None = None,
    ) -> list[uuid.UUID]:
        """
        Resolve the selector to a list of target document ids scoped to the collection.

        Args:
            collection_id (uuid.UUID): The collection every target must belong to.
            selector (DocumentSelector): The id-mode or filter-mode target set (validated shape).
            schema (Sequence[MetadataField]): The collection schema (for a filter-mode selector).
            limit (int | None): Cap the ids returned (None = every match). A destructive bulk op
                passes ``cap + 1`` so the caller can detect that more remain and signal it, rather
                than materialising an unbounded id set in memory.

        Returns:
            list[uuid.UUID]: The concrete target ids (may be empty when a filter matches nothing);
                at most ``limit`` when set.

        Raises:
            ValueError: In id mode, when an id is unknown or belongs to another collection; in filter
                mode, when a metadata field/operator is invalid (surfaced from the mapper).
        """
        # 1. Id mode — validate existence + collection ownership, never mutate across tenants. The
        #    explicit set is already bounded by the request body, so a limit only slices it.
        if selector.document_ids is not None:
            ids = await self._resolve_ids(collection_id, selector.document_ids)
            return ids if limit is None else ids[:limit]

        # 2. Filter mode — every matching id minus the deselected few (the mapper validates fields).
        return await self._resolve_filter(collection_id, selector, schema, limit)

    async def _resolve_ids(
        self, collection_id: uuid.UUID, wanted: Sequence[uuid.UUID]
    ) -> list[uuid.UUID]:
        """Validate an explicit id set against existence and collection scope."""
        documents = await self._database.documents.get_by_ids(list(wanted))
        found = {document.id for document in documents}
        missing = [str(value) for value in wanted if value not in found]
        if missing:
            raise ValueError(f"unknown document(s): {missing}")
        foreign = [
            str(document.id) for document in documents if document.collection_id != collection_id
        ]
        if foreign:
            raise ValueError(f"document(s) not in collection {collection_id}: {foreign}")
        return list(wanted)

    async def _resolve_filter(
        self,
        collection_id: uuid.UUID,
        selector: DocumentSelector,
        schema: Sequence[MetadataField],
        limit: int | None = None,
    ) -> list[uuid.UUID]:
        """Resolve a filter to the matching ids in the collection minus the deselected ids."""
        # 1. Build + validate the query spec (filter only). A ``limit`` bounds the DB projection so a
        #    huge match never loads every id; the order is id-stable for convergent re-runs.
        spec = CorpusMapper.to_spec(selector.filter, None, schema)
        matched = await self._database.documents.resolve_query_ids(collection_id, spec, limit)
        # 2. Drop the deselected ids (the UI's select-all-minus-N).
        excluded = set(selector.exclude_ids)
        return [document_id for document_id in matched if document_id not in excluded]


__all__ = ["DocumentSelectorResolver"]
