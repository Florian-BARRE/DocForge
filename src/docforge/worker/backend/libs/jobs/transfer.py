# ====== Code Summary ======
# The collection export/import arq tasks — the async, no-recompute movement of a whole collection
# between DocForge servers. export_collection streams the collection into a `.dcexport` bundle
# (blobs + vectors + Postgres rows), tars it (optionally zstd), and publishes it to S3 ATOMICALLY
# (a crash mid-export leaves only a throwaway temp dir, never a partial published object); it stamps
# the tracking row with the durable artifact reference the download endpoint reads. import_collection
# downloads a bundle, VALIDATES it (manifest + per-file checksums) before any write, then restores it
# as a BRAND-NEW collection with ids preserved (chunk id == Qdrant point id) — rolling the whole new
# collection back on any failure. Both drive their `collection_transfer` row RUNNING → DONE/FAILED.

# ====== Standard Library Imports ======
import pathlib
import shutil
import tempfile
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

# ====== Internal Project Imports ======
from collection_transfer import (
    BundleArchive,
    BundleReader,
    CollectionExporter,
    get_importer,
)

# ====== Internal Project Imports (worker) ======
from backend.context import CONTEXT
from shared_libs.services.db.s3 import S3ObjectApi

_BUNDLE_CONTENT_TYPE = "application/x-dcexport"


def _log_progress(stage: str, percent: int) -> None:
    """Engine progress callback — coarse tracing (the task writes milestone progress to the row)."""
    CONTEXT.logger.debug(f"transfer progress: {stage} {percent}%")


async def export_collection(
    ctx: dict[str, Any], collection_id: str, transfer_id: str
) -> dict[str, Any]:
    """
    Export a whole collection into a portable `.dcexport` bundle published to S3.

    Args:
        ctx (dict): arq's context dict (unused — services live on CONTEXT).
        collection_id (str): The collection to export (UUID as string; the queue carries strings).
        transfer_id (str): The pre-created ``collection_transfer`` row driving status + the artifact.

    Returns:
        dict: ``{s3_key, size_bytes, format_version, dense_dim, counts}`` — also stamped on the row.
    """
    database, s3, config = CONTEXT.database, CONTEXT.s3, CONTEXT.RUNTIME_CONFIG
    cid, tid = uuid.UUID(collection_id), uuid.UUID(transfer_id)
    await database.transfer_tracker.mark_running(tid, datetime.now(UTC))

    workspace = pathlib.Path(tempfile.mkdtemp(prefix="dcexport-"))
    work_dir, archive_path = workspace / "bundle", workspace / f"{tid}.dcexport"
    try:
        # 1. Stream the collection into the bundle tree, then archive it (temp only — nothing public).
        exporter = CollectionExporter(
            database.transfer,
            docforge_version=config.DOCFORGE_VERSION,
            created_at=datetime.now(UTC).isoformat(),
            compression=config.EXPORT_COMPRESSION,
            progress=_log_progress,
        )
        manifest = await exporter.build(cid, work_dir)
        await database.transfer_tracker.report_progress(tid, "archive", 90)
        BundleArchive.pack(work_dir, archive_path, config.EXPORT_COMPRESSION)

        # 2. Publish the finished object ATOMICALLY — the key becomes valid only once the PUT lands.
        key = f"{config.EXPORT_BUNDLE_PREFIX}/{tid}.dcexport"
        async with s3.client() as client:
            size = await S3ObjectApi.put_file(
                client, s3.bucket, key, archive_path, _BUNDLE_CONTENT_TYPE
            )

        # 3. Stamp the durable artifact reference + counts, then close the tracking row.
        counts = manifest.counts.model_dump()
        expires_at = (
            datetime.now(UTC) + timedelta(seconds=config.EXPORT_TTL_SECONDS)
            if config.EXPORT_TTL_SECONDS > 0
            else None
        )
        await database.transfer_tracker.set_artifact(
            tid,
            s3_key=key,
            size_bytes=size,
            format_version=manifest.format_version,
            dense_dim=manifest.dense_dim,
            counts=counts,
            expires_at=expires_at,
        )
        await database.transfer_tracker.mark_done(
            tid, datetime.now(UTC), collection_id=cid, counts=counts
        )
        CONTEXT.logger.info(
            f"Exported collection {collection_id} → {key} "
            f"({size} bytes, {counts.get('documents', 0)} docs, {counts.get('points', 0)} points)"
        )
        return {
            "s3_key": key,
            "size_bytes": size,
            "format_version": manifest.format_version,
            "dense_dim": manifest.dense_dim,
            "counts": counts,
        }
    except Exception as exc:
        CONTEXT.logger.exception(f"Export failed for collection {collection_id}: {exc}")
        await database.transfer_tracker.mark_failed(
            tid, f"{type(exc).__name__}: {exc}", datetime.now(UTC)
        )
        raise
    finally:
        shutil.rmtree(workspace, ignore_errors=True)


async def import_collection(
    ctx: dict[str, Any], s3_key: str, transfer_id: str, target_name: str | None = None
) -> dict[str, Any]:
    """
    Import a `.dcexport` bundle from S3 as a BRAND-NEW collection (no recompute, id-preserving).

    Args:
        ctx (dict): arq's context dict (unused — services live on CONTEXT).
        s3_key (str): The bundle object's key in S3.
        transfer_id (str): The pre-created ``collection_transfer`` row driving status.
        target_name (str | None): Optional name for the new collection (collision → renamed).

    Returns:
        dict: ``{collection_id, collection_name, counts}`` — also stamped on the tracking row.
    """
    database, s3 = CONTEXT.database, CONTEXT.s3
    tid = uuid.UUID(transfer_id)
    await database.transfer_tracker.mark_running(tid, datetime.now(UTC))

    workspace = pathlib.Path(tempfile.mkdtemp(prefix="dcimport-"))
    archive_path, extract_dir = workspace / "bundle.dcexport", workspace / "extracted"
    try:
        # 1. Download + extract, then VALIDATE (manifest + per-file checksums) BEFORE any write.
        async with s3.client() as client:
            await S3ObjectApi.download_to(client, s3.bucket, s3_key, archive_path)
        extract_dir.mkdir(parents=True, exist_ok=True)
        # Decompression-bomb guard: bound the extracted size to a multiple of the (already
        # upload-capped) compressed size, and cap the member count — a hostile high-ratio bundle is
        # refused mid-extraction instead of filling the worker's disk.
        config = CONTEXT.RUNTIME_CONFIG
        max_uncompressed = archive_path.stat().st_size * config.IMPORT_MAX_DECOMPRESSION_RATIO
        BundleArchive.unpack(
            archive_path,
            extract_dir,
            max_uncompressed_bytes=max_uncompressed,
            max_members=config.IMPORT_MAX_MEMBERS,
        )
        reader = BundleReader(extract_dir)
        manifest = reader.validate()
        await database.transfer_tracker.report_progress(tid, "restore", 10)

        # 2. Version-dispatched, transactional restore (rolls the new collection back on any failure).
        importer = get_importer(
            manifest.format_version, database.transfer, reader, progress=_log_progress
        )
        result = await importer.run(target_name)

        await database.transfer_tracker.mark_done(
            tid,
            datetime.now(UTC),
            collection_id=result.collection_id,
            collection_name=result.collection_name,
            counts=result.counts,
        )
        CONTEXT.logger.info(
            f"Imported bundle {s3_key} → collection {result.collection_id} "
            f"('{result.collection_name}')"
        )
        return {
            "collection_id": str(result.collection_id),
            "collection_name": result.collection_name,
            "counts": result.counts,
        }
    except Exception as exc:
        CONTEXT.logger.exception(f"Import failed for bundle {s3_key}: {exc}")
        await database.transfer_tracker.mark_failed(
            tid, f"{type(exc).__name__}: {exc}", datetime.now(UTC)
        )
        raise
    finally:
        shutil.rmtree(workspace, ignore_errors=True)


__all__ = ["export_collection", "import_collection"]
