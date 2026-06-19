# ====== Code Summary ======
# Repository for collection configuration mutations + version history.
# Owns: applying a config document to a collection (with pipeline_version bump + reindex flag),
# and the config_version audit log (snapshot / list / get) backing history + rollback.

# ====== Standard Library Imports ======
import re
import uuid
from typing import Any

# ====== Third-Party Library Imports ======
from loggerplusplus import LoggerClass
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

# ====== Local Project Imports ======
from ..models import CollectionModel, ConfigVersionModel, MetadataFieldModel


class ConfigRepository(LoggerClass):
    """Data-access layer for collection config changes and the ``config_version`` history."""

    def __init__(self) -> None:
        LoggerClass.__init__(self)

    # ─── Config mutation ─────────────────────────────────────────────────────────

    async def apply_config(
        self,
        session: AsyncSession,
        collection_id: uuid.UUID,
        doc: dict[str, Any],
        *,
        note: str | None = None,
    ) -> CollectionModel | None:
        """
        Apply a full config document to a collection and snapshot the result.

        Bumps ``pipeline_version`` when the pipeline or embedding model changed, sets
        ``needs_reindex`` when the embedding model changed (existing vectors become stale), and
        always re-injects the system metadata fields so they can never be lost.

        Args:
            session (AsyncSession): Active transactional session.
            collection_id (uuid.UUID): Target collection.
            doc (dict): A validated canonical config document (see ConfigDocument).
            note (str | None): Human note recorded in the version history.

        Returns:
            CollectionModel | None: The updated collection (metadata_fields loaded), or None.
        """
        # Imported lazily: config_validation pulls in libs.pipeline, which imports this storage
        # package — a module-level import here would create a circular import at startup.
        from libs.governance.config_validation import ConfigDocument

        # 1. Load current state (metadata_fields needed for ORM cascade replacement)
        collection = await self._get(session, collection_id)
        if collection is None:
            return None

        # 2. Detect changes that invalidate the vector space / require a version bump
        embed_changed = doc["embedding_model"] != collection.embedding_model
        pipeline_changed = doc["pipeline"] != (collection.pipeline or {})

        # 3. Apply contract + pipeline scalars
        collection.supported_formats = doc["supported_formats"]
        collection.max_file_size_bytes = doc["max_file_size_bytes"]
        collection.locality_policy = doc["locality_policy"]
        collection.embedding_model = doc["embedding_model"]
        collection.unknown_field_policy = doc["unknown_field_policy"]
        collection.pipeline = doc["pipeline"]
        if embed_changed or pipeline_changed:
            collection.pipeline_version = self._next_pipeline_version(collection.pipeline_version)
        if embed_changed:
            collection.needs_reindex = True

        # 4. Replace the metadata schema via the ORM relationship (delete-orphan cascade)
        merged_fields = ConfigDocument.merge_metadata_schema(doc.get("metadata_fields", []))
        collection.metadata_fields.clear()
        for spec in merged_fields:
            collection.metadata_fields.append(self._build_field(spec))
        await session.flush()

        # 5. Snapshot the applied config into the version history
        final_doc = {**doc, "metadata_fields": merged_fields}
        await self.snapshot(
            session, collection_id,
            pipeline_version=collection.pipeline_version, config=final_doc, note=note,
        )

        self.logger.info(
            f"Applied config to collection {collection_id} "
            f"(pipeline_version={collection.pipeline_version}, needs_reindex={collection.needs_reindex})"
        )
        return await self._get(session, collection_id)

    # ─── Version history ──────────────────────────────────────────────────────────

    async def snapshot(
        self,
        session: AsyncSession,
        collection_id: uuid.UUID,
        *,
        pipeline_version: str,
        config: dict[str, Any],
        note: str | None = None,
    ) -> ConfigVersionModel:
        """
        Append a config snapshot to the history (version = current max + 1).

        Args:
            session (AsyncSession): Active session.
            collection_id (uuid.UUID): Target collection.
            pipeline_version (str): The collection's pipeline_version at snapshot time.
            config (dict): The config document being recorded.
            note (str | None): Optional human note (e.g. "rollback to v2").

        Returns:
            ConfigVersionModel: The created snapshot row.
        """
        version = await self._next_version(session, collection_id)
        row = ConfigVersionModel(
            collection_id=collection_id, version=version,
            pipeline_version=pipeline_version, config=config, note=note,
        )
        session.add(row)
        await session.flush()
        return row

    async def list_versions(
        self, session: AsyncSession, collection_id: uuid.UUID
    ) -> list[ConfigVersionModel]:
        """Return all config snapshots for a collection, newest first."""
        result = await session.execute(
            select(ConfigVersionModel)
            .where(ConfigVersionModel.collection_id == collection_id)
            .order_by(ConfigVersionModel.version.desc())
        )
        return list(result.scalars().all())

    async def get_version(
        self, session: AsyncSession, collection_id: uuid.UUID, version: int
    ) -> ConfigVersionModel | None:
        """Fetch one config snapshot by (collection, version)."""
        result = await session.execute(
            select(ConfigVersionModel).where(
                ConfigVersionModel.collection_id == collection_id,
                ConfigVersionModel.version == version,
            )
        )
        return result.scalar_one_or_none()

    # ─── Private helpers ──────────────────────────────────────────────────────────

    async def _get(
        self, session: AsyncSession, collection_id: uuid.UUID
    ) -> CollectionModel | None:
        """Load a collection with its metadata_fields eagerly loaded."""
        result = await session.execute(
            select(CollectionModel)
            .options(selectinload(CollectionModel.metadata_fields))
            .where(CollectionModel.id == collection_id)
        )
        return result.scalar_one_or_none()

    async def _next_version(self, session: AsyncSession, collection_id: uuid.UUID) -> int:
        """Compute the next monotonic snapshot version for a collection (starts at 1)."""
        result = await session.execute(
            select(func.max(ConfigVersionModel.version)).where(
                ConfigVersionModel.collection_id == collection_id
            )
        )
        return int(result.scalar() or 0) + 1

    @staticmethod
    def _next_pipeline_version(current: str) -> str:
        """
        Increment the trailing integer of a pipeline_version tag (``v1`` → ``v2``).

        Falls back to appending ``-2`` when no trailing integer is present.
        """
        match = re.search(r"(\d+)$", current or "")
        if match:
            return f"{current[: match.start()]}{int(match.group(1)) + 1}"
        return f"{current or 'v1'}-2"

    @staticmethod
    def _build_field(spec: dict[str, Any]) -> MetadataFieldModel:
        """Build a MetadataFieldModel from a normalized metadata-field dict (no collection_id)."""
        return MetadataFieldModel(
            field_name=spec["field_name"],
            field_type=spec.get("field_type", "string"),
            required=bool(spec.get("required", False)),
            filterable=bool(spec.get("filterable", False)),
            lexical=bool(spec.get("lexical", False)),
            semantic=bool(spec.get("semantic", False)),
            enum_values=spec.get("enum_values"),
            is_system=bool(spec.get("is_system", False)),
        )
