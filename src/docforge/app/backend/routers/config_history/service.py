# ====== Code Summary ======
# ConfigHistoryService — the orchestration behind the /collections/{id}/config-versions routes: page
# the history with a per-version change summary, serve one snapshot MASKED, diff two snapshots, and
# RESTORE one. A restore re-applies the snapshot through the SAME write a PATCH ends in (secret
# resolution → canonicalize + structural validation → locked config-version write, compare-and-swap on
# the head read), so it mints a new version noted "restore of v{N}" and never rewrites history.

# ====== Standard Library Imports ======
import uuid

# ====== Third-Party Library Imports ======
from fastapi import HTTPException

# ====== Internal Project Imports ======
from shared_libs.pipelines.blob_secrets import redact_config_snapshot
from shared_libs.services.db.facades import ConfigAuthor, ConfigVersionConflictError
from shared_libs.services.db.postgresql.tables import ConfigVersion

# ====== Local Project Imports ======
from ...context import CONTEXT
from ...libs.config_history import ConfigDiffer, SnapshotSecretResolver
from ..collections.blob_helpers import CollectionBlobHelpers
from ..collections.helpers import CollectionHelpers
from .models import (
    ConfigDiffEntry,
    ConfigVersionDetail,
    ConfigVersionDiffResponse,
    ConfigVersionListResponse,
    ConfigVersionRestoreResponse,
    ConfigVersionSummary,
)


class ConfigHistoryService:
    """Static list / get / diff / restore of a collection's config versions."""

    def __new__(cls, *args: object, **kwargs: object) -> None:
        raise TypeError("ConfigHistoryService is a static-only class and cannot be instantiated.")

    @staticmethod
    def _summary(row: ConfigVersion, previous: ConfigVersion | None) -> ConfigVersionSummary:
        """The listing entry of one version, its changes summarised against its predecessor."""
        return ConfigVersionSummary(
            version=row.version,
            created_at=row.created_at,
            note=row.note,
            author_label=row.author_label,
            author_key_id=str(row.author_key_id) if row.author_key_id is not None else None,
            changes=ConfigDiffer.summary(previous.config if previous else None, row.config),
        )

    @staticmethod
    async def _require_collection(collection_id: uuid.UUID) -> None:
        """404 when the collection does not exist."""
        if await CONTEXT.database.collections.get(collection_id) is None:
            raise HTTPException(status_code=404, detail=f"Collection {collection_id} not found.")

    @staticmethod
    async def _version(collection_id: uuid.UUID, version: int) -> ConfigVersion:
        """One stored version, 404 when absent (real secrets — mask before serving)."""
        row = await CONTEXT.database.config_history.get(collection_id, version)
        if row is None:
            raise HTTPException(
                status_code=404,
                detail=f"Collection {collection_id}: config version {version} not found.",
            )
        return row

    @classmethod
    async def list_page(
        cls, collection_id: uuid.UUID, limit: int, offset: int
    ) -> ConfigVersionListResponse:
        """A newest-first page, each item summarised against the version just before it."""
        # 1. Existence, then the page (+ the predecessor of its oldest item).
        await cls._require_collection(collection_id)
        page = await CONTEXT.database.config_history.list_page(collection_id, limit, offset)
        # 2. Pair every item with its older neighbour (the next item, or the fetched predecessor).
        olders = [*page.items[1:], page.predecessor]
        items = [cls._summary(row, older) for row, older in zip(page.items, olders, strict=True)]
        return ConfigVersionListResponse(
            collection_id=str(collection_id),
            total=page.total,
            limit=limit,
            offset=offset,
            items=items,
        )

    @classmethod
    async def get(cls, collection_id: uuid.UUID, version: int) -> ConfigVersionDetail:
        """One version with its snapshot masked (the predecessor drives its change summary)."""
        row = await cls._version(collection_id, version)
        previous = (
            await CONTEXT.database.config_history.get(collection_id, version - 1)
            if version > 1
            else None
        )
        summary = cls._summary(row, previous)
        return ConfigVersionDetail(
            **summary.model_dump(), config=redact_config_snapshot(row.config) or {}
        )

    @classmethod
    async def diff(
        cls, collection_id: uuid.UUID, from_version: int, to_version: int
    ) -> ConfigVersionDiffResponse:
        """The structured masked diff from ``from_version`` to ``to_version``."""
        before = await cls._version(collection_id, from_version)
        after = await cls._version(collection_id, to_version)
        changes = [
            ConfigDiffEntry(path=c.path, op=c.op, before=c.before, after=c.after)
            for c in ConfigDiffer.diff(before.config, after.config)
        ]
        return ConfigVersionDiffResponse(
            collection_id=str(collection_id),
            from_version=from_version,
            to_version=to_version,
            changes=changes,
        )

    @classmethod
    async def restore(
        cls, collection_id: uuid.UUID, version: int, author: ConfigAuthor
    ) -> ConfigVersionRestoreResponse:
        """
        Re-apply a stored version as a NEW version through the PATCH write path.

        Raises:
            HTTPException: 404 unknown collection/version; 422 unmigratable or invalid snapshot;
                409 when another config write landed between the read and the write.
            SecretReentryRequired: A provider's current key lives at another endpoint (router → 422).
        """
        # 1. The CAS base (head version, then row) and the snapshot to restore.
        collection, head = await CONTEXT.database.collections.config_head(collection_id)
        if collection is None:
            raise HTTPException(status_code=404, detail=f"Collection {collection_id} not found.")
        snapshot = (await cls._version(collection_id, version)).config or {}

        # 2. Secrets: current same-endpoint key, else the snapshot's own; a moved endpoint raises.
        pipeline = SnapshotSecretResolver.resolve(snapshot.get("pipeline"), collection.pipeline)
        search = SnapshotSecretResolver.resolve(snapshot.get("search") or {}, collection.search)

        # 3. Fail-fast structural validation exactly like a PATCH (422 before any write).
        stored_pipeline = CollectionBlobHelpers.canonical_pipeline(pipeline or {})
        if search:
            CollectionHelpers.validate_search_blob(search, stored_pipeline)

        # 4. The locked config-version write, conditional on the head this restore was computed on.
        try:
            needs_reindex = await CONTEXT.database.collections.update_config(
                collection_id,
                pipeline=stored_pipeline,
                search=search,
                note=f"restore of v{version}",
                expected_version=head,
                author=author,
            )
        except ConfigVersionConflictError:
            raise HTTPException(
                status_code=409,
                detail=f"Collection {collection_id}: its config changed concurrently — retry the "
                f"restore of v{version}.",
            )
        return ConfigVersionRestoreResponse(
            collection_id=str(collection_id),
            restored_from=version,
            version=head + 1,
            needs_reindex=needs_reindex,
        )


__all__ = ["ConfigHistoryService"]
