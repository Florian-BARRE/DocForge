# ====== Code Summary ======
# Static helpers for the collection transfer router: spool a multipart bundle upload to S3 WITHOUT
# buffering a multi-GB file in RAM (stream → temp file → put_file), and build a human download
# filename for an exported bundle. Pure plumbing kept out of router.py per the FastAPI rules.

# ====== Standard Library Imports ======
from __future__ import annotations

import os
import pathlib
import re
import tempfile
from datetime import datetime
from typing import Any

# ====== Third-Party Library Imports ======
from fastapi import HTTPException, UploadFile
from loggerplusplus import loggerplusplus

_BUNDLE_CONTENT_TYPE = "application/x-dcexport"
_SLUG_RE = re.compile(r"[^a-z0-9]+")


class TransferHelpers:
    """Static helpers for staging a bundle upload and naming an export download."""

    logger = loggerplusplus.bind(identifier="TransferHelpers")
    # The window size for both the upload spool and the temp-file write.
    CHUNK_BYTES = 1024 * 1024

    def __new__(cls, *args: object, **kwargs: object) -> None:
        raise TypeError("TransferHelpers is a static-only class and cannot be instantiated.")

    @classmethod
    async def stage_upload(
        cls, file: UploadFile, s3_key: str, transfer: Any, max_bytes: int
    ) -> int:
        """
        Stream a multipart bundle upload to S3 under ``s3_key`` without holding it all in memory.

        The multipart body is spooled to a temp file in bounded windows (never the whole file in
        RAM), then published to S3 with a known Content-Length via the transfer façade's
        ``stage_bundle`` (a plain PUT of the open handle). The spool aborts with a 413 the instant the
        streamed size crosses ``max_bytes`` — an uncapped upload could exhaust the object store's disk
        (a DoS). Nothing reaches S3 until the whole body has been spooled, so an aborted upload leaves
        NO partial staged object; the temp file is always removed.

        Args:
            file (UploadFile): The multipart-uploaded bundle.
            s3_key (str): The staging object key to publish under.
            transfer (Any): The CollectionTransferFacade (CONTEXT.database.transfer).
            max_bytes (int): The hard ceiling on the streamed body (413 past it).

        Returns:
            int: The staged object's size in bytes.

        Raises:
            HTTPException: 413 the moment the spooled size exceeds ``max_bytes``.
        """
        # 1. Spool the upload to a temp file in bounded windows (no multi-GB RAM buffer), aborting the
        #    instant the ceiling is crossed — the S3 PUT below never runs, so nothing is staged.
        fd, tmp_path = tempfile.mkstemp(suffix=".dcexport")
        try:
            spooled = 0
            with os.fdopen(fd, "wb") as handle:
                while True:
                    chunk = await file.read(cls.CHUNK_BYTES)
                    if not chunk:
                        break
                    spooled += len(chunk)
                    if spooled > max_bytes:
                        raise HTTPException(
                            status_code=413,
                            detail=f"Import bundle exceeds the limit (> {max_bytes} bytes).",
                        )
                    handle.write(chunk)

            # 2. Publish the spooled file to S3 with a known Content-Length (streamed PUT).
            size = await transfer.stage_bundle(s3_key, tmp_path, _BUNDLE_CONTENT_TYPE)
            cls.logger.info(f"Staged import bundle → {s3_key} ({size} bytes)")
            return size
        finally:
            # 3. Reclaim the temp file regardless of outcome.
            pathlib.Path(tmp_path).unlink(missing_ok=True)

    @staticmethod
    def optional_form(value: str | None) -> str | None:
        """
        Normalize an optional multipart form field: an empty/blank string means 'not provided'.

        Args:
            value (str | None): The raw form value.

        Returns:
            str | None: The trimmed value, or None when absent/blank.
        """
        # 1. A multipart empty field arrives as "" — treat blank as absent.
        if value is None:
            return None
        trimmed = value.strip()
        return trimmed or None

    @classmethod
    def download_filename(cls, collection_name: str | None, when: datetime | None) -> str:
        """
        Build the ``Content-Disposition`` filename for a downloaded export bundle.

        Args:
            collection_name (str | None): The exported collection's name (may be None).
            when (datetime | None): The export completion time (falls back to now).

        Returns:
            str: A safe ``{slug}-{YYYYMMDD}.dcexport`` filename.
        """
        # 1. Slugify the collection name so the filename is filesystem/HTTP safe.
        slug = _SLUG_RE.sub("-", (collection_name or "collection").lower()).strip("-")
        slug = slug or "collection"

        # 2. Stamp the date (completion time, else now) and the bundle extension.
        stamp = (when or datetime.now()).strftime("%Y%m%d")
        return f"{slug}-{stamp}.dcexport"


__all__ = ["TransferHelpers"]
