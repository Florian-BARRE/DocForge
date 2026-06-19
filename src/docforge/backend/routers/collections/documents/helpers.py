# ====== Code Summary ======
# DocumentOps — shared document operations reused across the documents / reprocess / pages
# routers so single and batch variants apply identical logic (delete cascade, metadata merge +
# validation + targeted reindex, pipeline reingest, index-only reindex). Lives in the backend
# layer because it orchestrates via CONTEXT (the service locator).

# ====== Standard Library Imports ======
import uuid
from typing import Any

# ====== Third-Party Library Imports ======
from loggerplusplus import loggerplusplus

# ====== Internal Project Imports ======
from backend.context import CONTEXT
from libs.data.storage.s3.helpers import S3Helpers
from libs.governance.admission import AdmissionValidator

# Nodes re-run by an index-only reindex (chunk → contextualize → embed); parse/enrich stay cached.
_REINDEX_NODES: list[str] = ["s4", "s5", "s6"]


class DocumentOps:
    """Static document operations shared by the single-document and batch endpoints."""

    logger = loggerplusplus.bind(identifier="DocumentOps")

    def __new__(cls, *args: object, **kwargs: object) -> None:
        raise TypeError("DocumentOps is a static-only class and cannot be instantiated.")

    # ─── Delete ─────────────────────────────────────────────────────────────────

    @classmethod
    async def delete_cascade(
        cls, collection_id: uuid.UUID, document_id: uuid.UUID, source_hash: str
    ) -> dict[str, Any]:
        """
        Delete a document everywhere: Qdrant points, Postgres rows (cascade), shared-safe S3 blobs.

        Args:
            collection_id (uuid.UUID): Owning collection (== Qdrant collection name).
            document_id (uuid.UUID): Document to delete.
            source_hash (str): Content address of the original file.

        Returns:
            dict: ``{qdrant_points_deleted, blob_deleted}``.
        """
        # 1. Collect + delete the document's Qdrant points (point id == chunk id)
        qdrant_points_deleted = 0
        if CONTEXT.qdrant is not None:
            async with CONTEXT.postgres.session() as session:
                chunks = await CONTEXT.chunk_repo.get_by_document(session, document_id)
            point_ids = [str(c["id"]) for c in chunks]
            qdrant_points_deleted = await CONTEXT.qdrant.delete_points(str(collection_id), point_ids)

        # 2. Decide blob fate before deleting rows (shared blobs are kept)
        async with CONTEXT.postgres.session() as session:
            shared = await CONTEXT.document_repo.is_source_hash_used_by_other_documents(
                session, source_hash, document_id
            )

        # 3. Delete Postgres rows (cascade) + S3 blobs when this was the last reference
        async with CONTEXT.postgres.session() as session:
            await CONTEXT.document_repo.delete(session, document_id)
        blob_deleted = False
        if not shared:
            await CONTEXT.s3.delete(S3Helpers.key_original(source_hash))
            await CONTEXT.s3.delete_prefix(f"derived/{source_hash}/")
            blob_deleted = True

        cls.logger.info(
            f"Deleted document {document_id} (qdrant_points={qdrant_points_deleted}, blob_deleted={blob_deleted})"
        )
        return {"qdrant_points_deleted": qdrant_points_deleted, "blob_deleted": blob_deleted}

    # ─── Metadata ───────────────────────────────────────────────────────────────

    @classmethod
    async def apply_metadata(
        cls, collection: Any, doc: Any, patch: dict[str, Any], reindex: bool
    ) -> dict[str, Any]:
        """
        Merge a metadata patch (null removes a key), re-validate, persist, optionally reindex.

        Returns:
            dict: On success ``{user_meta, changed_fields, reindexed, index_sync, warning}``;
                on a contract break ``{"issues": [...]}`` (the caller maps it to HTTP 422).
        """
        # 1. Merge onto existing user_meta (null → remove)
        merged = dict(doc.user_meta or {})
        changed: set[str] = set()
        for key, value in patch.items():
            changed.add(key)
            if value is None:
                merged.pop(key, None)
            else:
                merged[key] = value

        # 2. Re-validate against the collection schema
        issues = AdmissionValidator.validate_metadata(collection, merged)
        if issues:
            return {"issues": issues}

        # 3. Persist
        async with CONTEXT.postgres.session() as session:
            await CONTEXT.document_repo.update_user_meta(session, doc.id, merged)

        # 4. Optional targeted index sync
        reindexed, warning, index_sync = False, None, None
        if reindex and changed:
            if doc.status != "done":
                warning = f"Document status is {doc.status!r}; no index to sync yet."
            elif CONTEXT.metadata_indexer is None:
                warning = "Embedding/index disabled (S6) — Postgres updated only."
            else:
                doc_meta = {**(doc.implicit_meta or {}), **merged}
                async with CONTEXT.postgres.session() as session:
                    index_sync = await CONTEXT.metadata_indexer.sync_document_fields(
                        session, collection_name=str(doc.collection_id), document_id=doc.id,
                        metadata_fields=collection.metadata_fields, doc_meta=doc_meta,
                        changed_field_names=changed,
                    )
                reindexed = True

        return {
            "user_meta": merged, "changed_fields": sorted(changed),
            "reindexed": reindexed, "index_sync": index_sync, "warning": warning,
        }

    # ─── Reprocess ──────────────────────────────────────────────────────────────

    @classmethod
    async def reingest(
        cls, doc: Any, *, force: bool = False, invalidate_nodes: list[str] | None = None
    ) -> uuid.UUID:
        """
        Re-enqueue the pipeline for a document and return the new job id.

        The Merkle node cache makes unchanged stages no-ops. ``force`` invalidates every cached
        node (full re-run); ``invalidate_nodes`` invalidates only the named nodes (e.g. reindex).

        Args:
            doc (Any): The document record to reprocess.
            force (bool): Drop all cached stage_runs so every stage re-executes.
            invalidate_nodes (list[str] | None): Specific node ids to invalidate.

        Returns:
            uuid.UUID: The new job id (also used as the arq job id, enabling cancel).
        """
        # 1. Bust the node cache as requested
        if force or invalidate_nodes:
            async with CONTEXT.postgres.session() as session:
                await CONTEXT.node_cache.invalidate_document(
                    session, doc.id, None if force else invalidate_nodes
                )

        # 2. Reset status + create a fresh job
        async with CONTEXT.postgres.session() as session:
            await CONTEXT.document_repo.update_status(session, doc.id, "pending")
        async with CONTEXT.postgres.session() as session:
            job = await CONTEXT.job_repo.create(
                session, document_id=doc.id, collection_id=doc.collection_id
            )
            job_id = job.id

        # 3. Enqueue (arq job id == our job id, so cancel can abort it)
        await CONTEXT.arq_pool.enqueue_job(
            "run_pipeline_task", document_id=str(doc.id), source_hash=doc.source_hash,
            filename=doc.filename, pipeline_version=doc.pipeline_version,
            job_id=str(job_id), collection_id=str(doc.collection_id), _job_id=str(job_id),
        )
        cls.logger.info(f"Reingest enqueued doc={doc.id} job={job_id} force={force} nodes={invalidate_nodes}")
        return job_id

    @classmethod
    async def reindex(cls, doc: Any) -> uuid.UUID:
        """Re-run only the index path (chunk → contextualize → embed) for a document."""
        return await cls.reingest(doc, invalidate_nodes=_REINDEX_NODES)
