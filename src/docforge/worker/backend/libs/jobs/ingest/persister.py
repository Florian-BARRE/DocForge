# ====== Code Summary ======
# Persister — the "translate and persist" steps shared by the full run and the replay run: the
# execution tree onto the job's stage timeline (FULL trace tier: raw payloads to the object store
# first, so the tree-persist stamps the refs), the IR → DB translation (RunTranslator over the
# bundle, the chunker strategy and the blob's config hash) and the safe persistence order of a full
# run — blobs (S3) → the one-tx save (PG) → the vectors (Qdrant). The replay run reuses the tree
# persist, the translation and the index, and saves downstream-only instead. Every write goes
# through the Database façades; nothing here touches a table, a bucket or a collection directly.

# ====== Standard Library Imports ======
import hashlib
import json
import uuid
from typing import Any

# ====== Local Project Imports ======
from persistence import RunTranslator

# ====== Internal Project Imports ======
from shared_libs.pipelines.engine import TraceLevel

# ====== Local Project Imports ======
from ..indexing import DocumentIndexer
from .ingest_services import IngestServices

_ZERO_CHUNK_WARNING = (
    "Ingestion completed but produced 0 chunks — nothing retrievable was created "
    "(the document may be empty or image-only with no extractable text)."
)


class Persister:
    """Translate a run's delivery and persist it through the Database façades."""

    def __init__(self, services: IngestServices) -> None:
        """
        Args:
            services (IngestServices): The run's services (database, config, logger).
        """
        self._services = services

    async def persist_execution_tree(
        self, job_id: uuid.UUID, record: Any, trace_level: TraceLevel
    ) -> None:
        """
        Persist the FULL per-node execution tree (nested + per-item ForEach instances, each with its
        quality score) onto the job's stage timeline.

        Done right after the run returns — before translate/persist, which may fail — so the trace
        is materialized whenever the run itself completed. For the FULL trace tier, each node's raw
        payload goes to the object store FIRST (best-effort, content-addressed, job-prefixed) so the
        tree-persist stamps the refs; the shape summaries ride on the record itself. A store miss
        just drops that ref — never fails an already-delivered run.
        """
        database = self._services.database
        refs = None
        if trace_level.captures_full:
            refs = await database.ingestion.store_trace_payloads(
                job_id, record, self._services.config.WORKER_TRACE_PAYLOAD_MAX_BYTES
            )
        await database.jobs.persist_execution_tree(job_id, record, refs=refs)

    @staticmethod
    def translate(doc_uuid: uuid.UUID, bundle: Any, schema: list[Any], blob: dict) -> Any:
        """Translate the delivery into the persistence payload (the SAME translator for both modes).

        Args:
            doc_uuid (uuid.UUID): The document the delivery belongs to.
            bundle (Any): The run's delivery bundle.
            schema (list[Any]): The collection's metadata field rows.
            blob (dict): The normalized pipeline blob (chunker strategy + config hash derive from it).

        Returns:
            Any: The RunTranslator output (objects, blob rows, payload, points, dense_dim, layout).
        """
        strategy = next(
            (
                node.get("kind", "")
                for node in blob.get("nodes", [])
                if isinstance(node, dict) and node.get("family") == "chunker"
            ),
            "unknown",
        )
        config_hash = hashlib.sha256(
            json.dumps(blob, sort_keys=True, default=str).encode()
        ).hexdigest()
        return RunTranslator.translate(doc_uuid, bundle, schema, strategy, config_hash)

    async def save_full(self, doc_uuid: uuid.UUID, translated: Any, bundle: Any) -> None:
        """
        Persist a full run in the safe order: blobs (S3) → the one-tx save (PG).

        A run that completed the whole graph but delivered zero chunks is a SUCCESS-with-warning,
        not a failure: the runner only returns here once every FAIL-policy node succeeded (a real
        upstream failure raised before this), so zero chunks means benign empty content (an
        image-only PDF with OCR off, a fail-soft OCR that dropped every page). The document is saved
        DONE with a visible "0 chunks" warning; a normal run passes None so a re-ingest wipes any
        stale warning.
        """
        database = self._services.database
        warning_reason = None if bundle.chunks else _ZERO_CHUNK_WARNING
        await database.ingestion.store_blobs(translated.objects, translated.blob_rows)
        await database.ingestion.save(doc_uuid, translated.payload, warning_reason=warning_reason)

    async def save_downstream(
        self,
        doc_uuid: uuid.UUID,
        translated: Any,
        *,
        replace_enrichments: bool,
        replace_document_meta: bool,
        warning_reason: str | None,
    ) -> None:
        """Persist a replay run: only the downstream layers (blocks/pages/blobs are never touched)."""
        await self._services.database.replay_persist.save_downstream(
            doc_uuid,
            translated.payload,
            replace_enrichments=replace_enrichments,
            replace_document_meta=replace_document_meta,
            warning_reason=warning_reason,
        )

    async def index(self, collection_id: uuid.UUID, doc_uuid: uuid.UUID, translated: Any) -> None:
        """Vectors (Qdrant) + the best-effort doc-scope denormalisations (shared with replay)."""
        await DocumentIndexer.index(
            self._services.database,
            collection_id,
            doc_uuid,
            translated,
            self._services.logger,
        )


__all__ = ["Persister"]
