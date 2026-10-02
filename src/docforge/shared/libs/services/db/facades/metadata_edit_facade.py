# ====== Code Summary ======
# MetadataEditFacade — the value-edit orchestration for a single document's DOCUMENT-SCOPE metadata,
# WITHOUT a full re-ingest. Validates each requested field against the collection's schema (exists,
# document-scope only, type/enum), partially upserts the new VALUES (DocumentApi.update_metadata),
# then SYNCHRONOUSLY repaints the filterable Qdrant payloads (FilterSyncFacade — pure set_payload,
# no embed). It returns which changed fields feed a named vector (semantic/lexical) so the caller
# can enqueue the lightweight per-document re-embed worker job — the embed is a provider/spend call
# that belongs at the worker edge, never in the request. Chunk-scope fields are rejected (a reindex,
# not a value-edit, is required). Never touches chunk CONTENT.

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

# ====== Local Project Imports ======
from .filter_sync_facade import FilterSyncFacade


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

    def __init__(self, postgres: PostgresClient, filter_sync: FilterSyncFacade) -> None:
        """
        Args:
            postgres (PostgresClient): The tabular truth (schema + the metadata values written here).
            filter_sync (FilterSyncFacade): Reused as-is to repaint the filterable Qdrant payloads
                synchronously (pure set_payload, no embed) after the values land.
        """
        LoggerClass.__init__(self)
        self._postgres = postgres
        self._filter_sync = filter_sync

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
    ) -> list[DocumentMetadata]:
        """
        Validate every requested field and build the rows to upsert (raises on any error).

        Args:
            values (dict[str, Any]): The requested field_name → new value map.
            by_name (dict[str, MetadataField]): The collection's schema, keyed by field name.

        Returns:
            list[DocumentMetadata]: The rows to upsert (field_id + value + the field's own origin).

        Raises:
            MetadataValidationError: When any field is unknown, chunk-scope, or carries a bad value.
        """
        # 1. Walk the requested fields, collecting precise errors (unknown / chunk-scope / bad value).
        #    USER and GENERATED document-scope fields are both accepted — a GENERATED override is
        #    allowed (it is overwritten again on the next reingest/metagen, which rewrites that set).
        errors: list[str] = []
        rows: list[DocumentMetadata] = []
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
            value_error = AdmissionHelpers.value_error(self.__spec_of(spec_row), value)
            if value_error is not None:
                errors.append(value_error)
                continue
            rows.append(DocumentMetadata(field_id=spec_row.id, value=value, origin=spec_row.origin))
        # 2. Any error → reject the WHOLE edit (all-or-nothing; a partial write would confuse callers).
        if errors:
            raise MetadataValidationError(errors)
        return rows

    async def update_document_metadata(
        self, document_id: uuid.UUID, values: dict[str, Any]
    ) -> MetadataEditResult:
        """
        Write new metadata VALUES on a document and repaint its filterable payloads synchronously.

        The cheap per-document value edit: no chunk content is re-embedded. The values are validated
        against the collection's schema, upserted in one transaction, and the filterable Qdrant
        payloads are repainted inline (pure set_payload, instant). The returned result names which
        changed fields feed a semantic/lexical named vector so the CALLER can enqueue the lightweight
        re-embed job (a provider/spend call that must run at the worker edge, not in the request).

        Args:
            document_id (uuid.UUID): The document to edit.
            values (dict[str, Any]): The requested field_name → new value map (document-scope only).

        Returns:
            MetadataEditResult: The written field names and the subset that needs a re-embed.

        Raises:
            MetadataEditNotFoundError: When the document no longer exists.
            MetadataValidationError: When any requested field fails validation.
        """
        # 1. Resolve the document + its collection's schema, validate, and upsert — ONE transaction.
        async with self._postgres.session() as session:
            document = await DocumentApi.get(session, document_id)
            if document is None:
                raise MetadataEditNotFoundError(document_id)
            schema = await CollectionApi.get_schema(session, document.collection_id)
            by_name = {row.field_name: row for row in schema}
            rows = self.__validate(values, by_name)
            # 2. Keep only the fields whose value actually DIFFERS from what is stored — a no-op edit
            #    (same value re-sent) must not spend a worker slot re-embedding identical vectors. The
            #    new value is NUL-stripped before the compare, matching how it will be persisted so a
            #    stripped-only diff never counts as a change.
            stored = {
                row.field_id: row.value
                for row in await DocumentApi.get_metadata(session, document_id)
            }
            changed = [
                r for r in rows if TextSanitizer.strip_nul(r.value) != stored.get(r.field_id)
            ]
            await DocumentApi.update_metadata(session, document_id, changed)
            # 3. Map the changed field ids back to names + flags WHILE the schema rows are live. A
            #    changed field feeding a named vector (semantic/lexical) needs its value re-embedded;
            #    a filterable-only change is fully handled by the sync below.
            spec_by_id = {row.id: row for row in schema}
            updated_fields = sorted(spec_by_id[r.field_id].field_name for r in changed)
            reembed_fields = sorted(
                spec_by_id[r.field_id].field_name
                for r in changed
                if spec_by_id[r.field_id].semantic or spec_by_id[r.field_id].lexical
            )

        # 4. Nothing actually changed → Qdrant already matches; no repaint, no job, truthful result.
        if not changed:
            self.logger.info(
                f"No metadata value changed on document {document_id} — nothing to sync"
            )
            return MetadataEditResult()

        # 5. Repaint the filterable payloads synchronously — pure set_payload, instant, no embed.
        #    BEST-EFFORT: the PG write above is already committed (the source of truth). A Qdrant
        #    hiccup must NOT surface the committed edit as a failure; instead we flag it so the caller
        #    schedules the durable repair job (mirrors the ingest index hook's best-effort denorm).
        filter_repaint_failed = False
        try:
            await self._filter_sync.sync_document_filter_payloads(document_id)
        except Exception:
            filter_repaint_failed = True
            self.logger.warning(
                f"Filterable repaint failed for document {document_id} after the metadata write "
                f"committed — scheduling the repair job to reconcile Qdrant",
                exc_info=True,
            )

        self.logger.info(
            f"Updated {len(updated_fields)} metadata value(s) on document {document_id} "
            f"(reembed fields: {reembed_fields or 'none'})"
        )
        return MetadataEditResult(
            updated_fields=updated_fields,
            reembed_fields=reembed_fields,
            filter_repaint_failed=filter_repaint_failed,
        )


__all__ = [
    "MetadataEditFacade",
    "MetadataEditNotFoundError",
    "MetadataValidationError",
    "MetadataEditResult",
]
