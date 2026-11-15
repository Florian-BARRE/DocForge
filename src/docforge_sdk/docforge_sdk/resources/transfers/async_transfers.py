# ====== Code Summary ======
# The asynchronous collection export/import — trigger, poll, and streamed bundle download resource:
# the awaiting shell over the shared ``_TransfersSpecs`` builders.

# ====== Standard Library Imports ======
from collections.abc import AsyncIterator
from pathlib import Path
from typing import IO

# ====== Local Project Imports ======
from ...models.transfers import TransferAccepted, TransferStatus
from .._base import AsyncResource
from .specs import _TransfersSpecs


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
