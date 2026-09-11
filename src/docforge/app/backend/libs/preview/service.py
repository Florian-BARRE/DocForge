# ====== Code Summary ======
# PreviewService — the app-side coordinator for an ingestion DRY-RUN against a real collection. It is
# the ingest analog of the SearchService: given a collection id + a source document (uploaded bytes or
# a rehydrated existing document) and an OPTIONAL candidate blob, it loads the collection + its schema,
# builds the run-input contract, resolves which blob to dry-run (the candidate, else the collection's
# stored pipeline, else the stock default) auto-healing it to the current engine, runs it INLINE via
# the PreviewRunner, and projects the bounded report. It NEVER persists: no document row, no S3 blob,
# no Qdrant point — the worker's RunTranslator is never invoked. A broken blob is a typed error (422).

# ====== Standard Library Imports ======
import uuid
from typing import Any

# ====== Third-Party Library Imports ======
from loggerplusplus import LoggerClass

# ====== Internal Project Imports ======
from shared_libs.pipelines.ingest import BlobNormalizer, IngestPipeline
from shared_libs.pipelines.ingest.estimate import RateTable
from shared_libs.pipelines.preview import (
    PreviewContractBuilder,
    PreviewProjector,
    PreviewResponse,
    PreviewRunner,
)
from shared_libs.public_models import SourceDocument
from shared_libs.services.db import Database

# A run that delivered no bundle (a failed/timed-out node) still returns a report — this module never
# raises for a run OUTCOME; it only raises PreviewGraphError/BlobNormalizationError for a bad BLOB.


class PreviewService(LoggerClass):
    """Coordinates one inline ingestion dry-run against a stored collection — persists nothing."""

    def __init__(
        self,
        database: Database,
        timeout_seconds: float,
        chunk_text_max_chars: int,
    ) -> None:
        """
        Args:
            database (Database): The shared data facade (collections + schema reads only).
            timeout_seconds (float): Wall-clock cap for one inline dry-run (the interactive guardrail).
            chunk_text_max_chars (int): Per-chunk text/context truncation ceiling in the report.
        """
        LoggerClass.__init__(self)
        self._database = database
        self._runner = PreviewRunner()
        self._timeout_seconds = timeout_seconds
        self._chunk_text_max_chars = chunk_text_max_chars

    def __resolve_blob(self, collection: Any, blob_override: dict | None) -> dict:
        """
        Pick + auto-heal the blob to dry-run: the candidate override, else the collection's stored
        pipeline, else the stock default — all normalized to the current engine topology.

        Args:
            collection (Any): The collection row (its ``pipeline`` is the stored blob).
            blob_override (dict | None): A candidate blob to preview instead of the stored one.

        Returns:
            dict: The plain-dict blob to run (always healed to the current engine).

        Raises:
            BlobNormalizationError: The chosen blob cannot be reconciled to the current engine.
        """
        # 1. An explicit candidate wins; else the stored pipeline; else the product's stock default.
        chosen = (
            blob_override
            or collection.pipeline
            or IngestPipeline.default_blob().model_dump(mode="json")
        )
        # 2. Heal registry drift at read — the same contract the worker applies before building.
        return BlobNormalizer.normalize(chosen)

    async def preview(
        self,
        collection_id: uuid.UUID,
        source: SourceDocument,
        *,
        max_chunks: int,
        blob_override: dict | None = None,
        collection: Any | None = None,
    ) -> PreviewResponse | None:
        """
        Dry-run the ingestion graph on one document and return the bounded report (nothing persisted).

        Args:
            collection_id (uuid.UUID): The collection whose contract + pipeline the run uses.
            source (SourceDocument): The source to run on (uploaded bytes or a rehydrated document).
            max_chunks (int): How many chunks to include in the report (already clamped by the router).
            blob_override (dict | None): A candidate blob to preview instead of the stored pipeline.
            collection (Any | None): The already-loaded collection row (avoids a second round-trip).

        Returns:
            PreviewResponse | None: The bounded report, or None when the collection is unknown (404).

        Raises:
            BlobNormalizationError: The chosen blob cannot be migrated to the current engine (422).
            PreviewGraphError: The blob is unbuildable/invalid or is not an ingestion pipeline (422).
        """
        # 1. The collection is the contract + pipeline source. Reuse the one the router loaded.
        if collection is None:
            collection = await self._database.collections.get(collection_id)
        if collection is None:
            return None

        # 2. Build the run-input contract + resolve the blob (candidate / stored / default, healed).
        schema = await self._database.collections.get_schema(collection_id)
        contract = PreviewContractBuilder.build(collection, schema)
        blob = self.__resolve_blob(collection, blob_override)

        # 3. Run inline under the wall-clock cap — a failed node returns (None, partial record) as DATA.
        bundle, record = await self._runner.run(
            blob, source, contract, timeout_seconds=self._timeout_seconds
        )

        # 4. Price the ACTUAL spend against the collection's effective rates (same numbers as the meter),
        #    then project the bounded report.
        rates = RateTable.from_overrides(getattr(collection, "estimate_overrides", None))
        return PreviewProjector.project(
            bundle,
            record,
            rates,
            source_filename=source.filename,
            max_chunks=max_chunks,
            text_max_chars=self._chunk_text_max_chars,
        )


__all__ = ["PreviewService"]
