# ====== Code Summary ======
# MetadataEditFacade — the value-edit orchestration for a single document's DOCUMENT-SCOPE metadata,
# WITHOUT a full re-ingest. Validates each requested field against the collection's schema (exists,
# document-scope only, type/enum), then partitions the request into SETS (a non-null value) and
# CLEARS (a null value). SETS are partially upserted (DocumentApi.update_metadata) and their
# filterable Qdrant payloads repainted SYNCHRONOUSLY (FilterSyncFacade — pure set_payload, no embed);
# a changed semantic/lexical SET field is reported so the caller can enqueue the lightweight
# per-document re-embed worker job (the embed is a provider/spend call that belongs at the worker
# edge, never in the request). CLEARS just REMOVE data — the PG row is deleted and the field's
# denormalised Qdrant footprint (filterable payload key and/or semantic/lexical named vectors) is
# removed SYNCHRONOUSLY in the request: a clear needs no embedder, no provider and no worker job.
# Chunk-scope fields are rejected (a reindex, not a value-edit, is required); clearing a REQUIRED
# field is rejected (a required field cannot be unset). Never touches chunk CONTENT.

# ====== Standard Library Imports ======
import uuid
from dataclasses import dataclass, field
from typing import Any

# ====== Third-Party Library Imports ======
from loggerplusplus import LoggerClass

# ====== Internal Project Imports ======
from shared_libs.pipelines.ingest.nodes.intake.admission.helpers import AdmissionHelpers
from shared_libs.public_models import FieldScope, MetadataFieldSpec, TextSanitizer
from shared_libs.services.db.postgresql import PostgresClient
from shared_libs.services.db.postgresql.apis import CollectionApi, DocumentApi
from shared_libs.services.db.postgresql.tables import DocumentMetadata, MetadataField
from shared_libs.services.db.qdrant import QdrantClient, QdrantIndexApi, VectorNames

# ====== Local Project Imports ======
from .filter_sync_facade import FilterSyncFacade
from .helpers import DatabaseHelpers


class MetadataEditNotFoundError(Exception):
    """Raised when the edited document is gone (deleted in the race window) — router maps to a 404."""

    def __init__(self, document_id: uuid.UUID) -> None:
        """
        Args:
            document_id (uuid.UUID): The document that could not be found.
        """
        super().__init__(f"Document {document_id} not found.")
        self.document_id = document_id


class MetadataValidationError(Exception):
    """Raised when one or more requested fields fail validation — the router maps it to a 422."""

    def __init__(self, errors: list[str]) -> None:
        """
        Args:
            errors (list[str]): The precise per-field validation messages (joined for the detail).
        """
        super().__init__("; ".join(errors))
        self.errors = errors


@dataclass(slots=True)
class MetadataEditResult:
    """The outcome of a value-edit — which fields were written and which need a re-embed."""

    updated_fields: list[str] = field(default_factory=list)
    reembed_fields: list[str] = field(default_factory=list)
    # The committed write is the source of truth; the inline filterable repaint is best-effort. When
    # it fails (Qdrant hiccup) the caller must schedule the durable repair job even for a
    # filterable-only edit, so the stale Qdrant payload gets reconciled rather than left wrong.
    filter_repaint_failed: bool = False


class MetadataEditFacade(LoggerClass):
    """Edit a single document's document-scope metadata values without a re-ingest."""

    def __init__(
        self, postgres: PostgresClient, filter_sync: FilterSyncFacade, qdrant: QdrantClient
    ) -> None:
        """
        Args:
            postgres (PostgresClient): The tabular truth (schema + the metadata values written here).
            filter_sync (FilterSyncFacade): Reused as-is to repaint the filterable Qdrant payloads
                synchronously (pure set_payload, no embed) after SET values land.
            qdrant (QdrantClient): The vector store, used directly to REMOVE a cleared field's
                denormalised footprint (payload key + named vectors) synchronously — a clear needs
                no embed, so it is fully handled in the request rather than at the worker edge.
        """
        LoggerClass.__init__(self)
        self._postgres = postgres
        self._filter_sync = filter_sync
        self._qdrant = qdrant

    @staticmethod
    def __spec_of(row: MetadataField) -> MetadataFieldSpec:
        """Project an ORM schema row onto the pure spec the shared value validator consumes."""
        return MetadataFieldSpec(
            field_name=row.field_name,
            field_type=row.field_type,
            required=row.required,
            filterable=row.filterable,
            lexical=row.lexical,
            semantic=row.semantic,
            origin=row.origin,
            scope=row.scope,
            enum_values=row.enum_values,
        )

    def __validate(
        self, values: dict[str, Any], by_name: dict[str, MetadataField]
    ) -> tuple[list[DocumentMetadata], list[MetadataField]]:
        """
        Validate every requested field, partitioning it into a SET (upsert) or a CLEAR (delete).

        A ``null`` value is a CLEAR request: it must UNSET the field (delete its row + Qdrant
        footprint). A null on a REQUIRED field is rejected — a required field cannot be unset. Any
        other value is a SET and is type/enum-checked exactly as before.

        Args:
            values (dict[str, Any]): The requested field_name → new value map (``null`` = clear).
            by_name (dict[str, MetadataField]): The collection's schema, keyed by field name.

        Returns:
            tuple[list[DocumentMetadata], list[MetadataField]]: The rows to upsert (SETs) and the
                schema rows to clear (CLEARs). Change-detection against the stored values happens in
                the caller, with the live schema rows still in hand.

        Raises:
            MetadataValidationError: When any field is unknown, chunk-scope, carries a bad value, or
                clears a required field.
        """
        # 1. Walk the requested fields, collecting precise errors (unknown / chunk-scope / bad value /
        #    required-clear). USER and GENERATED document-scope fields are both accepted — a GENERATED
        #    override is allowed (it is overwritten again on the next reingest/metagen).
        errors: list[str] = []
        set_rows: list[DocumentMetadata] = []
        clear_specs: list[MetadataField] = []
        for name, value in values.items():
            spec_row = by_name.get(name)
            if spec_row is None:
                errors.append(f"unknown field '{name}'")
                continue
            if spec_row.scope == FieldScope.CHUNK:
                errors.append(
                    f"field '{name}' is chunk-scope — its value lives per chunk, so a reindex is "
                    f"required (there is no cheap value-edit path)"
                )
                continue
            # 2. A null value is a CLEAR — allowed only for a non-required field (unsetting a required
            #    field would leave the document in an invalid state; a reingest would then reject it).
            if value is None:
                if spec_row.required:
                    errors.append(
                        f"field '{name}' is required and cannot be cleared (send a value instead)"
                    )
                    continue
                clear_specs.append(spec_row)
                continue
            # 3. A non-null value is a SET — type/enum-checked, then queued as a row to upsert.
            value_error = AdmissionHelpers.value_error(self.__spec_of(spec_row), value)
            if value_error is not None:
                errors.append(value_error)
                continue
            set_rows.append(
                DocumentMetadata(field_id=spec_row.id, value=value, origin=spec_row.origin)
            )
        # 4. Any error → reject the WHOLE edit (all-or-nothing; a partial write would confuse callers).
        if errors:
            raise MetadataValidationError(errors)
        return set_rows, clear_specs

    async def __repaint_set_filters(self, document_id: uuid.UUID) -> bool:
        """Repaint the document's filterable payloads for SET changes (best-effort; True on failure)."""
        try:
            await self._filter_sync.sync_document_filter_payloads(document_id)
            return False
        except Exception:
            self.logger.warning(
                f"Filterable repaint failed for document {document_id} after the metadata write "
                f"committed — scheduling the repair job to reconcile Qdrant",
                exc_info=True,
            )
            return True

    async def __clear_qdrant_footprint(
        self, document_id: uuid.UUID, qdrant_name: str, cleared: list[MetadataField]
    ) -> bool:
        """
        Remove each cleared field's denormalised Qdrant footprint (best-effort; True on failure).

        A cleared FILTERABLE field's payload key is deleted (it rides each point under its own
        ``field_name`` — the exact key FilterSyncFacade writes); a cleared SEMANTIC/LEXICAL field's
        ``meta_<slug>_dense`` / ``meta_<slug>_bm25`` named vectors are deleted. The content vectors
        are never named here, so they are untouched. A Qdrant hiccup is logged + flagged, never
        raised: the PG delete is already committed, so the stale footprint is reconciled by the
        repair job the caller schedules on the flag (the same denorm-drift class as a SET repaint).
        """
        # 1. Collect the payload keys (filterable) and named vectors (semantic/lexical) to drop.
        payload_keys = [spec.field_name for spec in cleared if spec.filterable]
        vector_names: list[str] = []
        for spec in cleared:
            if spec.semantic:
                vector_names.append(VectorNames.field_dense(spec.field_name))
            if spec.lexical:
                vector_names.append(VectorNames.field_sparse(spec.field_name))
        # 2. Delete them from every point of the document (each primitive no-ops on an empty list).
        try:
            await QdrantIndexApi.delete_payload(
                self._qdrant.raw, qdrant_name, payload_keys, document_id
            )
            await QdrantIndexApi.delete_vectors(
                self._qdrant.raw, qdrant_name, vector_names, document_id
            )
            return False
        except Exception:
            self.logger.warning(
                f"Clearing the Qdrant footprint failed for document {document_id} after the "
                f"metadata delete committed — scheduling the repair job to reconcile Qdrant",
                exc_info=True,
            )
            return True

    async def update_document_metadata(
        self, document_id: uuid.UUID, values: dict[str, Any]
    ) -> MetadataEditResult:
        """
        Write / clear metadata VALUES on a document and reconcile its Qdrant footprint synchronously.

        The cheap per-document value edit: no chunk content is re-embedded. Each field is validated
        against the collection's schema, then handled as a SET (non-null value) or a CLEAR (null):

        - SET: the value is upserted; its filterable payloads are repainted inline (pure set_payload,
          instant). A changed semantic/lexical SET field is named in ``reembed_fields`` so the CALLER
          enqueues the lightweight re-embed job (a provider/spend call, worker edge — not the request).
        - CLEAR: the field's row is deleted and its denormalised Qdrant footprint removed inline
          (payload key if filterable, named vectors if semantic/lexical). A clear needs no embed, so
          it never contributes to ``reembed_fields`` and never enqueues a job.

        Both the SET-upsert and the CLEAR-delete run in ONE transaction; the Qdrant reconciliation is
        best-effort (the PG write is the source of truth).

        Args:
            document_id (uuid.UUID): The document to edit.
            values (dict[str, Any]): The requested field_name → new value map (``null`` = clear).

        Returns:
            MetadataEditResult: The written/cleared field names and the SET subset needing a re-embed.

        Raises:
            MetadataEditNotFoundError: When the document no longer exists.
            MetadataValidationError: When any requested field fails validation.
        """
        # 1. Resolve the document + its collection's schema, validate, then write — ONE transaction.
        async with self._postgres.session() as session:
            document = await DocumentApi.get(session, document_id)
            if document is None:
                raise MetadataEditNotFoundError(document_id)
            schema = await CollectionApi.get_schema(session, document.collection_id)
            by_name = {row.field_name: row for row in schema}
            set_rows, clear_specs = self.__validate(values, by_name)
            # 2. Change-detect against the stored values. A SET is kept only when its value DIFFERS
            #    (a no-op re-send must not spend a worker slot); the NUL-strip matches how it will be
            #    persisted so a stripped-only diff never counts. A CLEAR acts only when the field
            #    CURRENTLY has a stored value — clearing an already-absent field is a clean no-op.
            stored = {
                row.field_id: row.value
                for row in await DocumentApi.get_metadata(session, document_id)
            }
            changed = [
                r for r in set_rows if TextSanitizer.strip_nul(r.value) != stored.get(r.field_id)
            ]
            cleared = [spec for spec in clear_specs if spec.id in stored]
            await DocumentApi.update_metadata(session, document_id, changed)
            await DocumentApi.delete_metadata(session, document_id, [spec.id for spec in cleared])
            # 3. Map the changed SET field ids back to names + flags WHILE the schema rows are live. A
            #    changed field feeding a named vector (semantic/lexical) needs its value re-embedded;
            #    a filterable-only change is fully handled by the repaint below.
            spec_by_id = {row.id: row for row in schema}
            updated_fields = sorted(
                [spec_by_id[r.field_id].field_name for r in changed]
                + [spec.field_name for spec in cleared]
            )
            reembed_fields = sorted(
                spec_by_id[r.field_id].field_name
                for r in changed
                if spec_by_id[r.field_id].semantic or spec_by_id[r.field_id].lexical
            )

        # 4. Nothing actually changed → Qdrant already matches; no repaint, no clear, truthful result.
        if not changed and not cleared:
            self.logger.info(
                f"No metadata value changed on document {document_id} — nothing to sync"
            )
            return MetadataEditResult()

        # 5. Reconcile Qdrant synchronously — the SET repaint (pure set_payload, no embed) and the
        #    CLEAR removal (delete payload key + named vectors). BEST-EFFORT: the PG write above is
        #    already committed (the source of truth). A Qdrant hiccup must NOT surface the committed
        #    edit as a failure; instead we flag it so the caller schedules the durable repair job
        #    (same denorm-drift class as the ingest index hook's best-effort denorm).
        qdrant_name = DatabaseHelpers.qdrant_collection_name(document.collection_id)
        sync_failed = False
        if changed:
            sync_failed |= await self.__repaint_set_filters(document_id)
        if cleared:
            sync_failed |= await self.__clear_qdrant_footprint(document_id, qdrant_name, cleared)

        self.logger.info(
            f"Updated {len(changed)} / cleared {len(cleared)} metadata value(s) on document "
            f"{document_id} (reembed fields: {reembed_fields or 'none'})"
        )
        return MetadataEditResult(
            updated_fields=updated_fields,
            reembed_fields=reembed_fields,
            filter_repaint_failed=sync_failed,
        )


__all__ = [
    "MetadataEditFacade",
    "MetadataEditNotFoundError",
    "MetadataValidationError",
    "MetadataEditResult",
]
