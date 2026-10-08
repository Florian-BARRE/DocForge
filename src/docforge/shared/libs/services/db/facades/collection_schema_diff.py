# ====== Code Summary ======
# CollectionSchemaDiff — the transactional metadata-schema diff staged INSIDE a caller-supplied
# session (never a wholesale replace: a CASCADE would destroy the stored values of unchanged fields),
# plus the display-title soft-reference upkeep it drags along: follow a renamed field, clear an
# orphaned one. Never opens nor commits a session.

# ====== Standard Library Imports ======
import uuid

# ====== Third-Party Library Imports ======
from loggerplusplus import loggerplusplus
from sqlalchemy.ext.asyncio import AsyncSession

# ====== Internal Project Imports ======
from shared_libs.public_models import FieldScope
from shared_libs.services.db.postgresql.apis import CollectionApi
from shared_libs.services.db.postgresql.tables import MetadataField


class CollectionSchemaDiff:
    """Static, session-scoped metadata-schema diff + title_field upkeep."""

    logger = loggerplusplus.bind(identifier="CollectionSchemaDiff")

    def __new__(cls, *args: object, **kwargs: object) -> None:
        raise TypeError("CollectionSchemaDiff is a static-only class and cannot be instantiated.")

    @staticmethod
    async def apply(
        session: AsyncSession,
        collection_id: uuid.UUID,
        desired: list[MetadataField],
        renames: dict[str, str] | None = None,
    ) -> None:
        """
        Diff-update the metadata schema INSIDE a caller-supplied session (never a wholesale replace).

        The transactional core shared by ``update_schema`` (own session) and ``apply_update`` (one
        session threaded through the whole PATCH). The caller MUST have already validated vector slugs
        (fail-fast, before any write). Never opens or commits a session — it only stages the writes;
        the caller then derives ``needs_reindex`` via ``CollectionConfigWriter.sync_needs_reindex`` over the final state.

        Args:
            session (AsyncSession): The unit of work the whole PATCH shares.
            collection_id (uuid.UUID): The collection.
            desired (list[MetadataField]): The target schema (collection_id filled here), keyed by the
                post-rename names.
            renames (dict[str, str] | None): Current name → new name. A renamed row is UPDATED in place
                (same id → its stored values survive), never deleted + re-added.
        """
        renames = renames or {}
        current = await CollectionApi.get_schema(session, collection_id)
        current_by_name = {row.field_name: row for row in current}
        desired_by_name = {row.field_name: row for row in desired}

        # 1. Delete the removed rows FIRST (values cascade — explicit) and flush, so a rename/add may
        #    reuse a freed name in this transaction without tripping the (collection, name) UNIQUE.
        #    A current row survives by name only when that name is not itself a rename's target.
        kept = set(desired_by_name) - set(renames.values())
        removed = [name for name in current_by_name if name not in kept and name not in renames]
        for name in removed:
            await session.delete(current_by_name.pop(name))
        if removed and renames:
            await session.flush()

        # 2. Renames in two phases (a temporary unique name, then the final one) so a chain or a swap
        #    never collides mid-flush; the row keeps its id, hence its document/chunk values.
        if renames:
            renamed = [current_by_name.pop(old) for old in renames]
            for row in renamed:
                row.field_name = f"__renaming_{row.id}"
            await session.flush()
            for row, new_name in zip(renamed, renames.values(), strict=True):
                row.field_name = new_name
                current_by_name[new_name] = row
            await session.flush()

        # 3. Update in place / insert new.
        for name, wanted in desired_by_name.items():
            row = current_by_name.get(name)
            if row is None:
                wanted.collection_id = collection_id
                session.add(wanted)
                continue
            row.field_type = wanted.field_type
            row.required = wanted.required
            row.filterable = wanted.filterable
            row.lexical = wanted.lexical
            row.semantic = wanted.semantic
            row.enum_values = wanted.enum_values
            row.origin = wanted.origin
            row.scope = wanted.scope
            # Documentation only — excluded from the index signature, so it never flags a reindex.
            row.description = wanted.description

    @staticmethod
    async def follow_renamed_title_field(
        session: AsyncSession, collection_id: uuid.UUID, renames: dict[str, str]
    ) -> None:
        """
        Point ``title_field`` at its field's new name when that field was renamed (same values).

        Args:
            session (AsyncSession): The unit of work the schema diff was staged on.
            collection_id (uuid.UUID): The collection whose setting may follow.
            renames (dict[str, str]): Current name → new name.
        """
        # 1. Only a title naming a renamed field moves; anything else is left to the orphan check.
        collection = await CollectionApi.get(session, collection_id)
        if collection is not None and collection.title_field in renames:
            collection.title_field = renames[collection.title_field]

    @classmethod
    async def clear_orphaned_title_field(
        cls, session: AsyncSession, collection_id: uuid.UUID
    ) -> str | None:
        """
        Clear the display-title field when the staged schema no longer has it as a document field.

        ``title_field`` is a SOFT reference (no FK) to a document-scope ``metadata_field``. A schema
        edit that removes or renames that field, or moves it to chunk scope, must not be blocked — so
        the dangling setting is cleared to NULL in the SAME transaction (the parsed title is shown
        again) and the cleared name is returned so the caller can report it. Must run AFTER the schema
        diff is staged on ``session`` (autoflush makes the staged rows visible to the read). The clear
        is logged as a warning, and the PATCH response shows ``title_field: null``.

        Args:
            session (AsyncSession): The unit of work the schema diff was staged on.
            collection_id (uuid.UUID): The collection whose setting is checked.

        Returns:
            str | None: The cleared field name, or None when the setting was unset or still valid.
        """
        # 1. Nothing configured → nothing can dangle.
        collection = await CollectionApi.get(session, collection_id)
        if collection is None or collection.title_field is None:
            return None

        # 2. Still a document-scope field of the post-diff schema → keep it.
        schema = await CollectionApi.get_schema(session, collection_id)
        if any(
            row.field_name == collection.title_field and row.scope == FieldScope.DOCUMENT
            for row in schema
        ):
            return None

        # 3. Orphaned → clear it alongside the schema edit and say so.
        cleared = collection.title_field
        collection.title_field = None
        cls.logger.warning(
            f"Collection {collection_id}: title_field '{cleared}' is no longer a document-scope "
            f"field after the schema change — cleared (documents show their parsed title again)"
        )
        return cleared


__all__ = ["CollectionSchemaDiff"]
