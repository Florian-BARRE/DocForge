# ====== Code Summary ======
# Rehydrator — step 1 of a run: load the inputs from the rows. The document row, its collection and
# metadata schema, the user-declared metadata, the ORIGINAL BYTES from S3 (key = source_hash — a replay
# never reads them: it stands on the persisted IR, so a garbage-collected source object must not fail
# it), the collection contract, the stored pipeline blob healed to the CURRENT engine topology, and the
# run's wall-clock budget + trace level. Reads only — no row is written here.

# ====== Standard Library Imports ======
import uuid
from typing import Any

# ====== Internal Project Imports ======
from shared_libs.pipelines.ingest import BlobNormalizationError, BlobNormalizer, IngestPipeline
from shared_libs.public_models import CollectionContract, MetadataFieldSpec, SourceDocument
from shared_libs.services.db.postgresql.tables import MetadataField
from shared_libs.services.db.s3 import S3ObjectApi

# ====== Local Project Imports ======
from .ingest_services import IngestServices
from .rehydrated_job import RehydratedJob
from .run_limits import RunLimits


class Rehydrator:
    """Load one run's inputs through the Database façade and S3."""

    def __init__(self, services: IngestServices) -> None:
        """
        Args:
            services (IngestServices): The run's services (database, s3, config, default timeout).
        """
        self._services = services

    @staticmethod
    def contract_from_rows(collection: Any, schema: list[MetadataField]) -> CollectionContract:
        """Build the pipeline's run-input contract from the collection + field rows."""
        return CollectionContract(
            collection_id=collection.id,
            name=collection.name,
            supported_formats=list(collection.supported_formats),
            max_file_size_bytes=collection.max_file_size_bytes,
            fields=[
                MetadataFieldSpec(
                    field_name=row.field_name,
                    field_type=row.field_type,
                    required=row.required,
                    filterable=row.filterable,
                    lexical=row.lexical,
                    semantic=row.semantic,
                    origin=row.origin,
                    scope=row.scope,
                )
                for row in schema
            ],
        )

    async def rehydrate(
        self, document_id: str, doc_uuid: uuid.UUID, replay_from: str | None
    ) -> RehydratedJob:
        """
        Load the document, collection, bytes (full run only), contract and normalized blob.

        Args:
            document_id (str): The document id as the queue carried it (for the error message).
            doc_uuid (uuid.UUID): The document's UUID.
            replay_from (str | None): The replay stage, or None for a full run (reads the S3 bytes).

        Returns:
            RehydratedJob: The run's inputs.

        Raises:
            RuntimeError: The document row is missing, or the stored blob cannot be auto-migrated.
            ValueError: The collection's job timeout exceeds the worker's hard ceiling.
        """
        database, s3 = self._services.database, self._services.s3
        config = self._services.config
        document = await database.documents.get(doc_uuid)
        if document is None:
            raise RuntimeError(f"document {document_id} not found")
        collection = await database.collections.get(document.collection_id)
        schema = await database.collections.get_schema(document.collection_id)
        # A replay never reads the original bytes (it stands on the persisted IR), so it does not
        # fetch them either — a garbage-collected source object must not fail a replay.
        raw = b""
        if not replay_from:
            async with s3.client() as client:
                raw = await S3ObjectApi.get(client, s3.bucket, document.source_hash)
        field_names = {row.id: row.field_name for row in schema}
        declared = {
            field_names[meta.field_id]: meta.value
            for meta in await database.documents.get_metadata(doc_uuid)
            if meta.origin.value == "user" and meta.field_id in field_names
        }
        source = SourceDocument(filename=document.filename, content=raw, declared_meta=declared)
        contract = self.contract_from_rows(collection, schema)

        # Normalize (auto-heal) the stored blob to the CURRENT engine topology before building the
        # graph: the expanded blob embeds engine-structural wiring that shifts when the engine
        # evolves, so a blob stored under an older engine is healed here rather than failing to
        # build. A blob that cannot be read back at all is a clear, collection-named error (recorded
        # on the job) — never a cryptic build crash after bytes are already stored.
        stored_blob = collection.pipeline or IngestPipeline.default_blob().model_dump(mode="json")
        try:
            blob = BlobNormalizer.normalize(stored_blob)
        except BlobNormalizationError as exc:
            raise RuntimeError(
                f"collection {collection.id} pipeline cannot be auto-migrated to the current "
                f"engine: {exc}"
            ) from exc

        # The run's wall-clock budget + effective trace level (shared by both run modes).
        timeout_seconds = RunLimits.resolve_job_timeout(
            collection.job_timeout_seconds,
            self._services.job_timeout_seconds,
            config.WORKER_JOB_TIMEOUT_MAX_SECONDS,
        )
        trace_level = RunLimits.resolve_trace_level(
            collection.trace_verbosity, config.WORKER_TRACE_MAX_VERBOSITY
        )
        return RehydratedJob(
            document=document,
            collection=collection,
            schema=schema,
            source=source,
            contract=contract,
            blob=blob,
            timeout_seconds=timeout_seconds,
            trace_level=trace_level,
        )


__all__ = ["Rehydrator"]
