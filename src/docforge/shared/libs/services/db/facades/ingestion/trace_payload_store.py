# ====== Code Summary ======
# TracePayloadStore — the FULL trace tier of an ingestion run: serialises every node's full
# input/output payload into content-addressed S3 objects under ``trace/{job_id}/``, records the stored
# footprint on the job row, and returns the per-node references the tree-persist step stamps onto the
# rows. Best-effort by contract (a store failure never fails an ingestion). Internal collaborator of
# IngestionFacade; callers go through ``Database.ingestion``.

# ====== Standard Library Imports ======
import hashlib
import json
import uuid

# ====== Third-Party Library Imports ======
from loggerplusplus import LoggerClass

# ====== Internal Project Imports ======
from shared_libs.pipelines.base import NodeExecutionRecord
from shared_libs.services.db.postgresql import PostgresClient
from shared_libs.services.db.postgresql.apis import JobApi
from shared_libs.services.db.postgresql.apis.execution_tree import (
    ExecutionTreeFlattener,
    TraceRefs,
)
from shared_libs.services.db.s3 import S3Client, S3Object, S3ObjectApi

# ====== Local Project Imports ======
from ..helpers import DatabaseHelpers


class TracePayloadStore(LoggerClass):
    """Store each node's full trace payload in the object store (best-effort)."""

    def __init__(self, postgres: PostgresClient, s3: S3Client) -> None:
        LoggerClass.__init__(self)
        self._postgres = postgres
        self._s3 = s3

    @staticmethod
    def _trace_object(payload: dict, key_prefix: str, max_payload_bytes: int) -> S3Object:
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
                obj = self._trace_object(node.record.resolved_input, prefix, max_payload_bytes)
                pending.append((node.node_path, "input", obj))
            if node.record.output is not None:
                obj = self._trace_object(node.record.output, prefix, max_payload_bytes)
                pending.append((node.node_path, "output", obj))
        if not pending:
            return {}

        # 2. One S3 client scope AND one put_many for the whole batch — up to ~60 sequential PUTs
        #    collapsed into a single call (content-addressed keys make repeated puts idempotent).
        #    Best-effort by contract: a batch failure is logged and drops every ref for this run (the
        #    rows simply keep no full payload), never failing an ingestion that already produced its
        #    bundle.
        input_by_path: dict[str, str] = {}
        output_by_path: dict[str, str] = {}
        try:
            async with self._s3.client() as s3:
                await S3ObjectApi.put_many(s3, self._s3.bucket, [obj for _, _, obj in pending])
        except Exception as exc:
            self.logger.warning(
                f"Trace payload store failed for job {job_id}; dropping {len(pending)} ref(s): {exc}"
            )
            return {}
        # ACCEPTED LIMITATION (rare, no code change): the caller stamps these refs onto the rows via
        # ``persist_execution_tree`` AFTER this returns. If that tree-persist fails, the S3 bytes are
        # written but no row flags ``has_full_*`` — the retention GC (which keys off those flags) then
        # never reclaims them, so they can strand. Rare (persist runs right after) and still reclaimable
        # by an explicit collection/document purge (it prefix-deletes ``trace/{job_id}/`` by job id,
        # not by flag); a full fix would need a two-phase commit not worth its weight here.
        for node_path, side, obj in pending:
            (input_by_path if side == "input" else output_by_path)[node_path] = obj.key

        # 3. Record the stored footprint on the job row (best-effort): the content-addressed objects
        #    are deduped by key (a payload reused across hops is stored — and counted — once), so the
        #    total mirrors what the ``trace/{job_id}/`` prefix physically holds. A persist failure is
        #    swallowed — trace accounting must never fail an ingestion that already produced its bundle.
        total_bytes = sum({obj.key: len(obj.data) for _, _, obj in pending}.values())
        try:
            async with self._postgres.session() as session:
                await JobApi.set_trace_payload_bytes(session, job_id, total_bytes)
        except Exception as exc:
            self.logger.warning(f"Trace payload byte accounting failed for job {job_id}: {exc}")

        # 4. Fold the two sides into one TraceRefs per node_path.
        paths = set(input_by_path) | set(output_by_path)
        return {
            path: TraceRefs(input_ref=input_by_path.get(path), output_ref=output_by_path.get(path))
            for path in paths
        }


__all__ = ["TracePayloadStore"]
