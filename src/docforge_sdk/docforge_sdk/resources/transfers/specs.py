# ====== Code Summary ======
# The transfers resource — collection export/import (trigger + poll + streamed bundle download). All
# URL/multipart logic lives once in the pure _TransfersSpecs mixin. The import upload STREAMS its file
# part (a path is opened, not read, so httpx pulls it from disk in bounded chunks) and the download
# STREAMS the response body (via the transport's stream_get) — neither buffers a multi-GB bundle whole
# in memory.

# ====== Standard Library Imports ======
from pathlib import Path
from typing import IO, Any

# ====== Local Project Imports ======
from ..._requestspec import RequestSpec
from .._base import _ResourceMixin


class _TransfersSpecs(_ResourceMixin):
    """Pure request/part builders for the transfers endpoints — the single source of URL/multipart logic."""

    _COLLECTIONS_PATH = "/collections"
    _TRANSFERS_PATH = "/transfers"

    def _export_spec(self, collection_id: str) -> RequestSpec:
        """
        Build the spec for opening an export of a whole collection.

        Args:
            collection_id (str): The collection to export.

        Returns:
            RequestSpec: A POST on the collection's ``/export`` sub-resource.
        """
        return RequestSpec("POST", f"{self._COLLECTIONS_PATH}/{collection_id}/export")

    def _get_spec(self, transfer_id: str) -> RequestSpec:
        """
        Build the spec for polling one transfer's status.

        Args:
            transfer_id (str): The transfer's UUID.

        Returns:
            RequestSpec: A GET on the transfer resource.
        """
        return RequestSpec("GET", f"{self._TRANSFERS_PATH}/{transfer_id}")

    def _download_path(self, transfer_id: str) -> str:
        """
        Build the API-relative path to a completed export's bundle bytes.

        Args:
            transfer_id (str): The transfer's UUID.

        Returns:
            str: The path to the transfer's ``/download`` sub-resource.
        """
        return f"{self._TRANSFERS_PATH}/{transfer_id}/download"

    @staticmethod
    def _import_parts(
        file: str | Path | bytes | IO[bytes],
        target_name: str | None,
    ) -> tuple[dict[str, Any], dict[str, str], IO[bytes] | None]:
        """
        Build the multipart ``files``/``data`` parts for a bundle import, streaming a path or file object.

        A path is OPENED, not read, so httpx pulls it from disk in bounded chunks rather than
        buffering the (possibly multi-GB) bundle in memory; raw bytes or a caller-supplied file
        object are passed through untouched (the caller owns that object's lifecycle either way).

        Args:
            file (str | Path | bytes | IO[bytes]): The ``.dcexport`` bundle — a local path, raw
                bytes, or an already-open binary file object.
            target_name (str | None): Optional name for the resulting collection.

        Returns:
            tuple[dict[str, Any], dict[str, str], IO[bytes] | None]: The httpx ``files`` mapping, the
            form ``data``, and the file handle THIS call opened (None unless a path was given) — the
            caller must close it once the request completes.
        """
        # 1. A path is opened lazily (never read()) so the multipart encoder streams it from disk.
        opened: IO[bytes] | None = None
        if isinstance(file, (str, Path)):
            path = Path(file)
            opened = path.open("rb")
            content: bytes | IO[bytes] = opened
            filename = path.name
        elif isinstance(file, bytes):
            content = file
            filename = "upload.dcexport"
        else:
            content = file
            filename = Path(str(getattr(file, "name", "upload.dcexport"))).name

        # 2. target_name is an optional form field — omitted entirely rather than sent as "None".
        files = {"file": (filename, content)}
        data = {"target_name": target_name} if target_name is not None else {}
        return files, data, opened
