# ====== Code Summary ======
# The transfers resource — collection export/import (trigger + poll + streamed bundle download). All
# URL/multipart logic lives once in the pure _TransfersSpecs mixin. The import upload STREAMS its file
# part (a path is opened, not read, so httpx pulls it from disk in bounded chunks) and the download
# STREAMS the response body (via the transport's stream_get) — neither buffers a multi-GB bundle whole
# in memory.

# ====== Standard Library Imports ======
from collections.abc import AsyncIterator, Iterator
from pathlib import Path
from typing import IO, Any

# ====== Local Project Imports ======
from .._requestspec import RequestSpec
from ..models.transfers import TransferAccepted, TransferStatus
from ._base import AsyncResource, SyncResource, _ResourceMixin


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


class AsyncTransfers(AsyncResource, _TransfersSpecs):
    """Asynchronous collection export/import — trigger, poll, and streamed bundle download."""

    async def export_collection(self, collection_id: str) -> TransferAccepted:
        """
        Open an asynchronous export of a whole collection into a portable ``.dcexport`` bundle.

        Args:
            collection_id (str): The collection to export.

        Returns:
            TransferAccepted: The transfer id, kind and pending status; poll it with ``get_transfer``.
        """
        return await self._transport.request(self._export_spec(collection_id), TransferAccepted)

    async def import_collection(
        self,
        file: str | Path | bytes | IO[bytes],
        target_name: str | None = None,
    ) -> TransferAccepted:
        """
        Import a ``.dcexport`` bundle as a brand-new collection (asynchronous, no recompute).

        The bundle is streamed to the server — a path is never read whole into memory.

        Args:
            file (str | Path | bytes | IO[bytes]): The bundle — a local path, raw bytes, or an
                already-open binary file object.
            target_name (str | None): Optional name for the resulting collection.

        Returns:
            TransferAccepted: The transfer id, kind and pending status; poll it with ``get_transfer``.
        """
        files, data, opened = self._import_parts(file, target_name)
        try:
            return await self._transport.upload(
                f"{self._COLLECTIONS_PATH}/import", files, data, TransferAccepted
            )
        finally:
            if opened is not None:
                opened.close()

    async def get_transfer(self, transfer_id: str) -> TransferStatus:
        """
        Poll one transfer's live status — progress, stage, counts, error, and (done export) artifact.

        Args:
            transfer_id (str): The transfer's UUID.

        Returns:
            TransferStatus: The transfer's status surface.
        """
        return await self._transport.request(self._get_spec(transfer_id), TransferStatus)

    async def download_export(self, transfer_id: str) -> AsyncIterator[bytes]:
        """
        Stream a completed export bundle's bytes in bounded chunks (never whole in memory).

        Args:
            transfer_id (str): The transfer's UUID.

        Yields:
            bytes: Successive chunks of the ``.dcexport`` bundle.
        """
        async for chunk in self._transport.stream_get(self._download_path(transfer_id)):
            yield chunk


class SyncTransfers(SyncResource, _TransfersSpecs):
    """Synchronous collection export/import — trigger, poll, and streamed bundle download."""

    def export_collection(self, collection_id: str) -> TransferAccepted:
        """
        Open an asynchronous export of a whole collection into a portable ``.dcexport`` bundle.

        Args:
            collection_id (str): The collection to export.

        Returns:
            TransferAccepted: The transfer id, kind and pending status; poll it with ``get_transfer``.
        """
        return self._transport.request(self._export_spec(collection_id), TransferAccepted)

    def import_collection(
        self,
        file: str | Path | bytes | IO[bytes],
        target_name: str | None = None,
    ) -> TransferAccepted:
        """
        Import a ``.dcexport`` bundle as a brand-new collection (asynchronous, no recompute).

        The bundle is streamed to the server — a path is never read whole into memory.

        Args:
            file (str | Path | bytes | IO[bytes]): The bundle — a local path, raw bytes, or an
                already-open binary file object.
            target_name (str | None): Optional name for the resulting collection.

        Returns:
            TransferAccepted: The transfer id, kind and pending status; poll it with ``get_transfer``.
        """
        files, data, opened = self._import_parts(file, target_name)
        try:
            return self._transport.upload(
                f"{self._COLLECTIONS_PATH}/import", files, data, TransferAccepted
            )
        finally:
            if opened is not None:
                opened.close()

    def get_transfer(self, transfer_id: str) -> TransferStatus:
        """
        Poll one transfer's live status — progress, stage, counts, error, and (done export) artifact.

        Args:
            transfer_id (str): The transfer's UUID.

        Returns:
            TransferStatus: The transfer's status surface.
        """
        return self._transport.request(self._get_spec(transfer_id), TransferStatus)

    def download_export(self, transfer_id: str) -> Iterator[bytes]:
        """
        Stream a completed export bundle's bytes in bounded chunks (never whole in memory).

        Args:
            transfer_id (str): The transfer's UUID.

        Yields:
            bytes: Successive chunks of the ``.dcexport`` bundle.
        """
        yield from self._transport.stream_get(self._download_path(transfer_id))


__all__ = ["AsyncTransfers", "SyncTransfers"]
