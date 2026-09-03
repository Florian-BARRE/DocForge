# ====== Code Summary ======
# SnippetApplier — the store-side follow-through of applying a config snippet to a collection, kept
# out of router.py so the route stays orchestration. It reuses the SAME collection-write machinery a
# PATCH goes through (secret restore, pipeline canonicalize+validate, embed-space reindex detection,
# search-blob validation, schema diff + store reconcile) so a snippet import can never drift from a
# normal config edit. Pure validation lives in SnippetHelpers; the pure blob logic in the collections
# package's helpers — this class only sequences them and touches the store via CONTEXT.

# ====== Third-Party Library Imports ======
from loggerplusplus import loggerplusplus

# ====== Internal Project Imports ======
from shared_libs.pipelines.blob_secrets import restore_blob_secrets
from shared_libs.services.db.postgresql.tables import Collection

# ====== Local Project Imports ======
from ...context import CONTEXT
from ..collections.blob_helpers import CollectionBlobHelpers
from ..collections.helpers import CollectionHelpers
from ..collections.store_sync import CollectionStoreSync
from .helpers import SnippetHelpers
from .models import SnippetKind


class SnippetApplier:
    """Static store-side follow-through for applying a config snippet (pipeline / search / schema)."""

    logger = loggerplusplus.bind(identifier="SnippetApplier")

    def __new__(cls, *args: object, **kwargs: object) -> None:
        raise TypeError("SnippetApplier is a static-only class and cannot be instantiated.")

    @classmethod
    async def apply(cls, collection: Collection, kind: SnippetKind, body: dict) -> bool:
        """
        Apply an unwrapped snippet body to a collection, reusing the normal config-edit path.

        Args:
            collection (Collection): The target collection row (the merge base for secret restore).
            kind (SnippetKind): The config slice being applied.
            body (dict): The snippet's unwrapped body (blob dict, or {'fields': [...]} for a schema).

        Returns:
            bool: Whether the applied change flags a reindex requirement.

        Raises:
            HTTPException: 422 on a broken pipeline / search graph / malformed schema snippet.
            ValueError: On a vector-slug collision in the applied schema (router maps to 422).
        """
        # 1. Route to the kind-specific applier — each mirrors the matching arm of the PATCH.
        if kind == "pipeline":
            return await cls.__apply_pipeline(collection, body)
        if kind == "search":
            return await cls.__apply_search(collection, body)
        return await cls.__apply_schema(collection, body)

    @classmethod
    async def __apply_pipeline(cls, collection: Collection, body: dict) -> bool:
        """Apply a pipeline snippet: restore secrets → canonicalize+validate → store (+reindex flag)."""
        # 1. Restore any masked provider secret from the CURRENT pipeline by node id (a masked key means
        #    "keep the stored one"). Cross-collection ids won't match, so those masks survive and the
        #    provider must be re-keyed — a snippet is config, not a secret carrier.
        healed = restore_blob_secrets(body, collection.pipeline) or {}

        # 2. Heal to the current engine + structurally validate (a broken graph is a clean 422 here).
        canonical = CollectionBlobHelpers.canonical_pipeline(healed)

        # 3. A change to the embed vector space forces a reindex (new docs would embed incompatibly).
        needs_reindex = CollectionBlobHelpers.embed_space_changed(collection.pipeline, canonical)

        # 4. Store the canonical blob + append the immutable version snapshot (None leaves the flag).
        await CONTEXT.database.collections.update_config(
            collection.id,
            pipeline=canonical,
            needs_reindex=True if needs_reindex else None,
            note="snippet import: pipeline",
        )
        return needs_reindex

    @classmethod
    async def __apply_search(cls, collection: Collection, body: dict) -> bool:
        """Apply a search snippet: restore secrets → validate (unless {}) → store. Never a reindex."""
        # 1. Restore masked secrets from the current search blob; {} stays the stock-default sentinel.
        healed = restore_blob_secrets(body, collection.search) or {}

        # 2. A non-empty search blob is validated as a genuine SEARCH graph before it can be stored.
        if healed != {}:
            CollectionHelpers.validate_search_blob(healed)

        # 3. Store it + snapshot; a search-graph change never invalidates the vector space (no reindex).
        await CONTEXT.database.collections.update_config(
            collection.id,
            search=healed,
            note="snippet import: search",
        )
        return False

    @classmethod
    async def __apply_schema(cls, collection: Collection, body: dict) -> bool:
        """Apply a schema snippet: parse fields → guard → diff-update the schema → reconcile the store."""
        # 1. Parse + guard the field specs exactly as a PATCH does (a malformed spec is a 422).
        fields = SnippetHelpers.body_to_fields(body)
        CollectionHelpers.validate_fields(fields)

        # 2. Diff-update the schema (existing values on untouched fields survive; ValueError → 422).
        reindex = await CONTEXT.database.collections.update_schema(
            collection.id, CollectionHelpers.to_field_rows(fields)
        )

        # 3. Reconcile the Qdrant store to the new schema + enqueue the idempotent repair backfills.
        await CollectionStoreSync.reconcile_and_backfill(collection.id)
        return reindex


__all__ = ["SnippetApplier"]
