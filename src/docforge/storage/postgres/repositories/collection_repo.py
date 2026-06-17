# ====== Code Summary ======
# Repository for CollectionModel: creation, retrieval, listing.

# ====== Standard Library Imports ======
import uuid
from typing import Any

# ====== Third-Party Library Imports ======
from loggerplusplus import LoggerClass
from sqlalchemy import delete as sa_delete
from sqlalchemy import select
from sqlalchemy import update as sa_update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

# ====== Local Project Imports ======
from ..models import CollectionModel, DocumentModel, MetadataFieldModel, StageRunModel


class CollectionRepository(LoggerClass):
    """Data-access layer for the ``collection`` table."""

    def __init__(self) -> None:
        LoggerClass.__init__(self)

    async def create(
        self,
        session: AsyncSession,
        *,
        name: str,
        supported_formats: list[str],
        max_file_size_bytes: int,
        locality_policy: str,
        embedding_model: str,
        pipeline: dict[str, Any] | None = None,
        pipeline_version: str = "v1",
        default_search: dict[str, Any] | None = None,
        unknown_field_policy: str = "reject",
        allowed_providers: list[str] | None = None,
        metadata_fields: list[dict[str, Any]] | None = None,
    ) -> CollectionModel:
        """
        Persist a new collection and return the created record.

        Args:
            session (AsyncSession): Active transactional session.
            name (str): Unique human-readable name.
            supported_formats (list[str]): Accepted file extensions (e.g. ["pdf", "docx"]).
            max_file_size_bytes (int): Maximum ingestion file size.
            locality_policy (str): ``on_premise_only`` or ``external_allowed``.
            embedding_model (str): Fixed embedding model for this collection's vector space.
            pipeline (dict | None): Serialized PipelineConfig.
            pipeline_version (str): Version tag.
            default_search (dict | None): Serialized SearchConfig defaults.
            unknown_field_policy (str): How to handle extra metadata fields.
            allowed_providers (list[str] | None): Allowlist when external_allowed.

        Returns:
            CollectionModel: The created and flushed record.
        """
        # 1. Build model
        collection = CollectionModel(
            name=name,
            supported_formats=supported_formats,
            max_file_size_bytes=max_file_size_bytes,
            unknown_field_policy=unknown_field_policy,
            locality_policy=locality_policy,
            allowed_providers=allowed_providers or [],
            pipeline=pipeline or {},
            pipeline_version=pipeline_version,
            embedding_model=embedding_model,
            default_search=default_search or {},
        )

        # 2. Persist the collection (flush to allocate its id for the FK)
        session.add(collection)
        await session.flush()

        # 3. Persist the metadata schema (3-flags + weights per field), if provided
        for spec in metadata_fields or []:
            session.add(
                MetadataFieldModel(
                    collection_id=collection.id,
                    field_name=spec["field_name"],
                    field_type=spec.get("field_type", "string"),
                    required=bool(spec.get("required", False)),
                    filterable=bool(spec.get("filterable", False)),
                    lexical=bool(spec.get("lexical", False)),
                    semantic=bool(spec.get("semantic", False)),
                    enum_values=spec.get("enum_values"),
                    is_system=bool(spec.get("is_system", False)),
                )
            )
        await session.flush()

        self.logger.info(
            f"Created collection id={collection.id} name={name!r} "
            f"metadata_fields={len(metadata_fields or [])}"
        )
        return collection

    async def delete(self, session: AsyncSession, collection_id: uuid.UUID) -> bool:
        """
        Delete a collection and all its DB rows.

        FK ON DELETE CASCADE handles metadata_field, document → block/chunk/job. stage_run has
        no cascade (it references document_id without a FK constraint), so its rows for the
        collection's documents are removed explicitly first.

        Args:
            session (AsyncSession): Active transactional session.
            collection_id (uuid.UUID): Primary key of the collection to delete.

        Returns:
            bool: True if a collection row was deleted, False if it did not exist.
        """
        # 1. Remove orphan-prone stage_run rows for this collection's documents
        doc_ids = select(DocumentModel.id).where(DocumentModel.collection_id == collection_id)
        await session.execute(sa_delete(StageRunModel).where(StageRunModel.document_id.in_(doc_ids)))

        # 2. Delete the collection (cascades documents/blocks/chunks/jobs/metadata_field)
        result = await session.execute(sa_delete(CollectionModel).where(CollectionModel.id == collection_id))
        return (result.rowcount or 0) > 0

    async def get_by_id(
        self, session: AsyncSession, collection_id: uuid.UUID
    ) -> CollectionModel | None:
        """
        Fetch a collection by UUID, eagerly loading its metadata_fields.

        Args:
            session (AsyncSession): Active session.
            collection_id (uuid.UUID): Primary key.

        Returns:
            CollectionModel | None: The collection with metadata_fields, or None.
        """
        result = await session.execute(
            select(CollectionModel)
            .options(selectinload(CollectionModel.metadata_fields))
            .where(CollectionModel.id == collection_id)
        )
        return result.scalar_one_or_none()

    async def list_all(self, session: AsyncSession) -> list[CollectionModel]:
        """
        Return all collections ordered by creation date (newest first).

        Args:
            session (AsyncSession): Active session.

        Returns:
            list[CollectionModel]: All collections.
        """
        result = await session.execute(
            select(CollectionModel).order_by(CollectionModel.created_at.desc())
        )
        return list(result.scalars().all())

    async def update_pipeline_version(
        self,
        session: AsyncSession,
        collection_id: uuid.UUID,
        pipeline_version: str,
        pipeline: dict[str, Any] | None = None,
    ) -> CollectionModel | None:
        """
        Bump the pipeline_version (and optionally update the pipeline config).

        Callers use this before scheduling a reindex so documents created after
        the update carry the new version tag.

        Args:
            session (AsyncSession): Active session.
            collection_id (uuid.UUID): Target collection.
            pipeline_version (str): New version string (e.g. "v2").
            pipeline (dict | None): Updated pipeline config; None = keep existing.

        Returns:
            CollectionModel | None: The updated collection, or None if not found.
        """
        # 1. Build update values
        values: dict[str, Any] = {"pipeline_version": pipeline_version}
        if pipeline is not None:
            values["pipeline"] = pipeline

        # 2. Execute update
        await session.execute(
            sa_update(CollectionModel)
            .where(CollectionModel.id == collection_id)
            .values(**values)
        )
        await session.flush()

        # 3. Return refreshed record
        result = await session.execute(
            select(CollectionModel).where(CollectionModel.id == collection_id)
        )
        collection = result.scalar_one_or_none()
        if collection:
            self.logger.info(
                f"CollectionRepository: pipeline_version={pipeline_version!r} "
                f"for collection id={collection_id}"
            )
        return collection

    async def list_document_ids(
        self,
        session: AsyncSession,
        collection_id: uuid.UUID,
        status_filter: str | None = "done",
    ) -> list[uuid.UUID]:
        """
        Return all document IDs belonging to a collection.

        Used by the reindex endpoint to enumerate documents that need re-embedding.

        Args:
            session (AsyncSession): Active session.
            collection_id (uuid.UUID): Target collection.
            status_filter (str | None): If set, only return docs with this status.
                Default "done" — only fully processed docs are eligible for reindex.

        Returns:
            list[uuid.UUID]: Ordered list of document UUIDs (oldest first).
        """
        query = select(DocumentModel.id).where(
            DocumentModel.collection_id == collection_id
        )
        if status_filter is not None:
            query = query.where(DocumentModel.status == status_filter)
        query = query.order_by(DocumentModel.created_at)

        result = await session.execute(query)
        return list(result.scalars().all())
