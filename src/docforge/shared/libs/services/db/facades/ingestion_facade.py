# ====== Code Summary ======
# IngestionFacade — the worker's persistence path, in pipeline order: dedup lookup, admission
# (document + job), blob storage (S3 then registry), the ONE-TRANSACTION save of everything a pure
# pipeline run produced (facts + pages + metadata + IR + chunks — idempotent on re-ingest via the
# purge-then-insert pattern), and the vector indexing (ensure the Qdrant collection from the schema,
# delete the document's stale points, upsert the fresh ones, flag the chunks indexed). Re-ingest is
# a REPLACE at every layer: Postgres purges-then-inserts, and Qdrant deletes-by-document before
# upsert (the run remints chunk ids, so a plain upsert would orphan the previous run's points).

# ====== Standard Library Imports ======
import hashlib
import json
import uuid
from collections.abc import Sequence

# ====== Internal Project Imports ======
from loggerplusplus import LoggerClass
from sqlalchemy.exc import IntegrityError

from shared_libs.pipelines.base import NodeExecutionRecord
from shared_libs.services.db.postgresql import PostgresClient
from shared_libs.services.db.postgresql.apis import (
    BlobApi,
    ChunkApi,
    CollectionApi,
    DocumentApi,
    IRApi,
    JobApi,
)
from shared_libs.services.db.postgresql.apis.execution_tree import (
    ExecutionTreeFlattener,
    TraceRefs,
)
from shared_libs.services.db.postgresql.tables import (
    Blob,
    Document,
    DocumentMetadata,
    DocumentStatus,
    Job,
)
from shared_libs.services.db.qdrant import (
    QdrantClient,
    QdrantCollectionApi,
    QdrantIndexApi,
    QdrantPoint,
)
from shared_libs.services.db.s3 import S3Client, S3Object, S3ObjectApi

# ====== Local Project Imports ======
from .helpers import DatabaseHelpers
from .payloads import AdmissionResult, IngestionPayload, ReingestOutcome, ReingestResult
from .trace_purge import TracePurgeHelper

# The document UNIQUE constraint a concurrent duplicate upload violates. Its name is stable via the
# schema naming convention (uq_<table>_<first-column>) → ``UniqueConstraint(collection_id, source_hash,
# pipeline_version)`` on ``document``. asyncpg exposes the violated constraint name on its native
# error, which under SQLAlchemy's adapter is the wrapper's ``__cause__`` (``error.orig`` itself carries
# none), so both hops are inspected. Matching the name tells a lost admission race apart from any other
# integrity failure (which must still surface as a real error).
_DOCUMENT_UNIQUE_CONSTRAINT = "uq_document_collection_id"


class IngestionFacade(LoggerClass):
    """The worker's persistence path — admit, store blobs, save the run, index the vectors."""

    def __init__(self, postgres: PostgresClient, qdrant: QdrantClient, s3: S3Client) -> None:
        LoggerClass.__init__(self)
        self._postgres = postgres
        self._qdrant = qdrant
        self._s3 = s3

    @staticmethod
    def _is_duplicate_document(error: IntegrityError) -> bool:
        """
        Decide whether an IntegrityError is the document UNIQUE-guard violation (a lost admission race).

        Args:
            error (IntegrityError): The error raised by the admission INSERT's flush.

        Returns:
            bool: True only when the violated constraint is ``uq_document_collection_id``.
        """
        # 1. Walk the driver error and its __cause__ (the asyncpg native error carrying constraint_name)
        #    and match the document guard's name — precise, so an unrelated integrity failure is never
        #    treated as a benign duplicate.
        orig = getattr(error, "orig", None)
        candidates = (orig, getattr(orig, "__cause__", None))
        return any(
            getattr(candidate, "constraint_name", None) == _DOCUMENT_UNIQUE_CONSTRAINT
            for candidate in candidates
        )

    async def find_duplicate(
        self, collection_id: uuid.UUID, source_hash: str, pipeline_version: str
    ) -> Document | None:
        """Dedup lookup — the already-ingested document for this exact content+config, or None."""
        async with self._postgres.session() as session:
            return await DocumentApi.find(session, collection_id, source_hash, pipeline_version)

    async def admit(
        self,
        document: Document,
        job: Job,
        declared_metadata: Sequence[DocumentMetadata] = (),
    ) -> AdmissionResult:
        """
        Register the document (PENDING), its ingestion job and its DECLARED metadata — one tx.

        The declared (user-origin) metadata is part of the admission: the worker reads it back
        to rebuild the pipeline's run input, so a half-admitted document must never exist.

        CONCURRENCY: two uploads of the same (collection, source_hash, pipeline_version) can both pass
        the router's dedup pre-check, then race here — the loser violates the document UNIQUE
        constraint. That is caught and resolved idempotently to the already-admitted document (no job),
        so a client retry never sees a 500. Any OTHER integrity failure is re-raised as a real error.

        Args:
            document (Document): The document row to create (status PENDING).
            job (Job): The ingestion job row (document/collection ids filled here).
            declared_metadata (Sequence[DocumentMetadata]): User-declared field rows
                (document_id filled here).

        Returns:
            AdmissionResult: ``created=True`` + the fresh document/job when this call won the insert;
                ``created=False`` + the incumbent document (no job) on a lost duplicate race.
        """
        # 1. Capture the dedup identity BEFORE the insert — after a failed flush + rollback the ORM
        #    object's attributes may be expired, so the incumbent re-query reads plain locals.
        collection_id = document.collection_id
        source_hash = document.source_hash
        pipeline_version = document.pipeline_version
        async with self._postgres.session() as session:
            # 2. Insert the document; a UNIQUE violation is a concurrent duplicate admission.
            try:
                created = await DocumentApi.create(session, document)
            except IntegrityError as error:
                # 3. Re-raise anything that is NOT our duplicate guard — a real, unexpected failure.
                if not self._is_duplicate_document(error):
                    raise
                # 4. Lost the race: reset the aborted transaction, then return the incumbent document.
                await session.rollback()
                existing = await DocumentApi.find(
                    session, collection_id, source_hash, pipeline_version
                )
                return AdmissionResult(created=False, document=existing)
            # 5. Won the insert — mint the job and persist the declared metadata in the same tx.
            job.document_id = created.id
            job.collection_id = created.collection_id
            created_job = await JobApi.create(session, job)
            if declared_metadata:
                for row in declared_metadata:
                    row.document_id = created.id
                await DocumentApi.replace_metadata(session, created.id, list(declared_metadata))
        return AdmissionResult(created=True, document=created, job=created_job)

    async def reingest(self, document_id: uuid.UUID) -> ReingestResult:
        """
        Re-enqueue ingestion for an EXISTING document — no re-upload needed.

        The original bytes are content-addressed (``source_hash``) and the worker refetches them,
        the collection's CURRENT pipeline is read at run time, and a run is idempotent (the previous
        chunks/IR/pages are purged in ``save`` and the previous Qdrant points are deleted-by-document
        in ``index`` before the fresh points are upserted — a REPLACE, never an accumulation). So
        re-processing a document — e.g. after a pipeline or engine change — is just a fresh job on
        the same document, reset to PENDING. The USER-declared metadata rows survive (never touched
        here).

        CONCURRENCY GUARD: a document that already has a live (PENDING/RUNNING) job is REFUSED
        (``ALREADY_ACTIVE``) rather than given a second job — two parallel runs of one document
        interleave their Qdrant delete-by-document + upsert and strand the loser's points as live
        orphans. The document row is locked ``FOR UPDATE`` for the admission so two concurrent
        reingests serialise: the second blocks, then sees the first's fresh PENDING job and refuses.

        Args:
            document_id (uuid.UUID): The document to re-ingest.

        Returns:
            ReingestResult: ADMITTED (+ document + fresh job) when a run was minted; NOT_FOUND for an
                unknown id; ALREADY_ACTIVE (+ the blocking job id) when a run is already in flight.
        """
        async with self._postgres.session() as session:
            # 1. Lock the row so a concurrent reingest of the same document can't also pass step 2.
            document = await DocumentApi.get_for_update(session, document_id)
            if document is None:
                return ReingestResult(outcome=ReingestOutcome.NOT_FOUND)
            # 2. Refuse a duplicate run while one is already queued or executing.
            active = await JobApi.get_active_for_document(session, document_id)
            if active is not None:
                return ReingestResult(
                    outcome=ReingestOutcome.ALREADY_ACTIVE, active_job_id=active.id
                )
            # 3. Capture the document's PRIOR job ids (before minting the fresh one) — the run being
            #    replaced; their full-trace payloads are reclaimed after the commit.
            prior_job_ids = await JobApi.list_job_ids_for_document(session, document_id)
            # 4. Mint the fresh job and reset the document to PENDING (one transaction).
            job = Job(document_id=document.id, collection_id=document.collection_id)
            created_job = await JobApi.create(session, job)
            await DocumentApi.set_status(session, document_id, DocumentStatus.PENDING)
        # 5. Reclaim the superseded runs' full-trace payloads (best-effort — the old job rows survive
        #    a reingest, so this also clears their now-dangling refs; a failure never blocks the run).
        await TracePurgeHelper.purge(self._postgres, self._s3, prior_job_ids)
        return ReingestResult(outcome=ReingestOutcome.ADMITTED, document=document, job=created_job)

    async def store_blobs(self, objects: Sequence[S3Object], rows: Sequence[Blob]) -> None:
        """
        Store blob bytes in S3, then register them in Postgres.

        S3 first: if the registry write then fails, the orphan S3 objects are harmless; the
        reverse order would register rows whose bytes do not exist.
        """
        # 1. The bytes.
        if objects:
            async with self._s3.client() as s3:
                await S3ObjectApi.put_many(s3, self._s3.bucket, objects)
        # 2. The registry rows — one bulk insert (idempotent per content hash).
        async with self._postgres.session() as session:
            await BlobApi.register_many(session, rows)

    @staticmethod
    def __trace_object(payload: dict, key_prefix: str, max_payload_bytes: int) -> S3Object:
        """Serialise one full trace payload to a content-addressed S3 object (truncated over the cap).

        The key is ``{key_prefix}{sha256}`` (the prefix ends with ``/``) so an unchanged IR reused
        across hops content-addresses to the SAME object (stored once), and a later GC can
        prefix-delete the whole ``trace/{job_id}/`` space. A payload whose serialised form exceeds
        ``max_payload_bytes`` is replaced by a compact truncation marker (the row's shape summary
        already describes the true payload).
        """
        raw = json.dumps(payload, default=str).encode()
        if len(raw) > max_payload_bytes:
            marker = {
                "_truncated": True,
                "original_bytes": len(raw),
                "preview": raw[:max_payload_bytes].decode(errors="replace"),
            }
            raw = json.dumps(marker).encode()
        digest = hashlib.sha256(raw).hexdigest()
        return S3Object(key=f"{key_prefix}{digest}", data=raw, content_type="application/json")

    async def store_trace_payloads(
        self, job_id: uuid.UUID, record: NodeExecutionRecord, max_payload_bytes: int
    ) -> dict[str, TraceRefs]:
        """
        Store each node's FULL input/output payload in the object store (the full trace tier).

        Walks the execution tree, serialises every full payload the engine attached (it does so ONLY
        at ``TraceLevel.FULL``), content-addresses it under a job-prefixed key ``trace/{job_id}/{hash}``
        (an unchanged IR reused across hops is stored once; a later GC prefix-deletes the whole job),
        and returns the per-node-path references the tree-persist step stamps onto the rows.

        Best-effort by contract: a store failure is logged and dropped (that node simply keeps no
        ref / ``has_full`` false) — trace capture must NEVER fail an ingestion that already produced
        its bundle. A payload over ``max_payload_bytes`` is stored truncated behind a marker.

        Args:
            job_id (uuid.UUID): The job whose trace payloads are stored (its key prefix).
            record (NodeExecutionRecord): The run's outermost execution record.
            max_payload_bytes (int): Per-payload byte cap; a larger serialised payload is truncated.

        Returns:
            dict[str, TraceRefs]: Per node_path, the object-store keys of its stored input/output
                payloads (a side is absent when the node had no full payload or the store missed).
        """
        # 1. Collect every full payload the engine attached (full tier only), keyed by node_path/side.
        prefix = DatabaseHelpers.trace_prefix(job_id)
        pending: list[tuple[str, str, S3Object]] = []
        for node in ExecutionTreeFlattener.flatten(record):
            if node.record.resolved_input is not None:
                obj = self.__trace_object(node.record.resolved_input, prefix, max_payload_bytes)
                pending.append((node.node_path, "input", obj))
            if node.record.output is not None:
                obj = self.__trace_object(node.record.output, prefix, max_payload_bytes)
                pending.append((node.node_path, "output", obj))
        if not pending:
            return {}

        # 2. One S3 client scope for the whole batch; each put is best-effort (a miss just drops that
        #    payload's ref). Content-addressed keys make repeated puts of the same bytes idempotent.
        input_by_path: dict[str, str] = {}
        output_by_path: dict[str, str] = {}
        async with self._s3.client() as s3:
            for node_path, side, obj in pending:
                try:
                    await S3ObjectApi.put_many(s3, self._s3.bucket, [obj])
                except Exception as exc:
                    self.logger.warning(
                        f"Trace payload store failed for {node_path}/{side} (job {job_id}); "
                        f"dropping its ref: {exc}"
                    )
                    continue
                (input_by_path if side == "input" else output_by_path)[node_path] = obj.key

        # 3. Fold the two sides into one TraceRefs per node_path.
        paths = set(input_by_path) | set(output_by_path)
        return {
            path: TraceRefs(input_ref=input_by_path.get(path), output_ref=output_by_path.get(path))
            for path in paths
        }

    async def save(
        self,
        document_id: uuid.UUID,
        payload: IngestionPayload,
        warning_reason: str | None = None,
    ) -> None:
        """
        Persist everything a pipeline run produced, in ONE transaction.

        Idempotent on re-ingest: the document's previous chunks and IR are purged first, then the
        fresh rows inserted, so re-running the same document never conflicts on primary keys.

        Re-ingest also PURGES superseded blobs. Postgres and Qdrant are REPLACED here, but blobs are
        content-addressed and only ever added (``store_blobs`` ran before this) — so a re-ingest whose
        renders/crops/canonical-PDF differ byte-wise (a config or engine change) would leak the old
        objects in S3 + the registry forever. So the set of blobs the document referenced BEFORE the
        purge is snapshotted, and after the fresh rows land any of those now-unreferenced (re-checked
        at delete time, so a hash still shared by another document is kept) is removed — mirroring the
        document DELETE path. The original source bytes survive (still referenced by ``source_hash``).

        Args:
            document_id (uuid.UUID): The admitted document.
            payload (IngestionPayload): The run's rows + learned facts.
            warning_reason (str | None): A non-fatal warning to stamp on the DONE document — set by
                the worker when a run completed cleanly but delivered zero chunks (nothing
                retrievable). None (the normal path) clears any stale warning on re-ingest.
        """
        async with self._postgres.session() as session:
            # 0. Snapshot the blobs the document references NOW — the supersede candidates, gathered
            #    BEFORE the purge so the OLD renders/crops/canonical-PDF are captured.
            superseded_candidates = await BlobApi.collect_hashes_for_document(session, document_id)
            # 1. The facts the pipeline learned about the document.
            await DocumentApi.update_facts(
                session,
                document_id,
                title=payload.title,
                language=payload.language,
                page_count=payload.page_count,
                source_kind=payload.source_kind,
                pdf_blob_hash=payload.pdf_blob_hash,
                simhash=payload.simhash,
            )
            # 2. Pages + document-scope metadata (replace semantics).
            await DocumentApi.replace_pages(session, document_id, payload.pages)
            await DocumentApi.replace_metadata(session, document_id, payload.document_metadata)
            # 3. Purge the previous run's chunks and IR (re-ingest idempotency), then insert fresh.
            await ChunkApi.delete_for_document(session, document_id)
            await IRApi.delete_for_document(session, document_id)
            await IRApi.persist_ir(
                session,
                payload.blocks,
                block_tables=payload.block_tables,
                block_figures=payload.block_figures,
                enrichments=payload.enrichments,
            )
            await ChunkApi.persist_chunks(
                session,
                payload.chunks,
                payload.composition,
                metadata=payload.chunk_metadata,
            )
            # 4. The persisted truth is complete — unless a force-cancel raced in (guarded DONE). The
            #    chunk count is denormalized here (0 for the empty case) and the optional warning is
            #    stamped so a 0-chunk run reads as DONE-with-warning, not FAILED.
            await DocumentApi.finalize_done(
                session,
                document_id,
                warning_reason=warning_reason,
                chunk_count=len(payload.chunks),
            )
            # 5. Purge the blobs this run superseded: flush so the FRESH pages/figures/PDF hashes are
            #    visible to the reference re-check, then delete only the old hashes nothing references
            #    anymore (a byte-identical render re-used across runs, or the source, is kept).
            await session.flush()
            orphans = await BlobApi.delete_unreferenced(session, superseded_candidates)
        # 6. S3 last, AFTER the commit — a failed object delete only leaves harmless orphan bytes.
        if orphans:
            async with self._s3.client() as s3:
                await S3ObjectApi.delete_many(s3, self._s3.bucket, orphans)
        self.logger.info(
            f"Ingestion saved for document {document_id}: "
            f"{len(payload.blocks)} blocks, {len(payload.chunks)} chunks "
            f"({len(orphans)} superseded blob(s) purged)"
        )

    async def mark_processing(self, document_id: uuid.UUID) -> None:
        """
        Move the document PENDING → PROCESSING as the worker claims its job.

        Guarded to the PENDING → PROCESSING edge (see ``DocumentApi.mark_processing``): the terminal
        DONE/FAILED writes at the end of the run always win, so a failure mid-run never leaves the
        document stuck in PROCESSING.
        """
        async with self._postgres.session() as session:
            await DocumentApi.mark_processing(session, document_id)

    async def mark_failed(self, document_id: uuid.UUID) -> None:
        """Flag the document's ingestion as failed (the job carries the error detail)."""
        async with self._postgres.session() as session:
            await DocumentApi.set_status(session, document_id, DocumentStatus.FAILED)

    async def index(
        self,
        collection_id: uuid.UUID,
        document_id: uuid.UUID,
        dense_dim: int,
        points: Sequence[QdrantPoint],
    ) -> None:
        """
        Push a document's chunk vectors into Qdrant (replacing its old points) and flag them indexed.

        The Qdrant collection is ensured (lazily created) from the CURRENT metadata schema; a
        dimension change without reindex surfaces as a loud upsert error, never silently. Because
        each run mints FRESH chunk point ids (the translator's chunk-UUID remap), a re-ingest's new
        points would NOT overwrite the previous run's — so the document's old points are deleted
        first (scoped to this one document_id), making a re-ingest a REPLACE, not an accumulation.
        On a first ingest the delete is a harmless no-op (the document has no points yet).

        Args:
            collection_id (uuid.UUID): The target collection.
            document_id (uuid.UUID): The document whose points these are — its stale points are
                purged first so a re-ingest never orphans the previous run's vectors.
            dense_dim (int): Dense vector dimension (from the pipeline's embed config).
            points (Sequence[QdrantPoint]): The points (ids = chunk ids) with vectors + payload.
        """
        # 1. Derive the vector space from the schema (and re-check the slug guard defensively).
        async with self._postgres.session() as session:
            schema = await CollectionApi.get_schema(session, collection_id)
        DatabaseHelpers.validate_vector_slugs(schema)
        name = DatabaseHelpers.qdrant_collection_name(collection_id)
        await QdrantCollectionApi.ensure(
            self._qdrant.raw,
            name,
            dense_dim=dense_dim,
            semantic_fields=[f.field_name for f in schema if f.semantic],
            lexical_fields=[f.field_name for f in schema if f.lexical],
            filterable_fields={
                f.field_name: DatabaseHelpers.payload_type_for(f.field_type)
                for f in schema
                if f.filterable
            },
        )
        # 2. Purge this document's previous points BEFORE upserting the fresh ones — the run remints
        #    chunk ids, so without this a re-ingest would leave the old points orphaned (live
        #    document_id + enabled payload → polluting the candidate pool and growing Qdrant
        #    unbounded). Scoped to the single document; a first ingest deletes nothing.
        await QdrantIndexApi.delete_by_document(self._qdrant.raw, name, document_id)
        # 3. Upsert, then flag the chunks as indexed.
        await QdrantIndexApi.upsert(self._qdrant.raw, name, points)
        async with self._postgres.session() as session:
            await ChunkApi.mark_indexed(session, [uuid.UUID(point.point_id) for point in points])
        self.logger.info(f"Indexed {len(points)} points into '{name}'")


__all__ = ["IngestionFacade"]
