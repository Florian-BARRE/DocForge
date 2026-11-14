"""R-11 — the worker reaches S3 only through the Database façades. These pin the façade side: each
new method performs EXACTLY the object-store operation the worker used to issue directly (same
bucket, same key, same arguments), so only the call path changed, never the S3 effect."""

import pathlib
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock

from shared_libs.services.db.facades import documents_facade as documents_module
from shared_libs.services.db.facades import transfer_facade as transfer_module
from shared_libs.services.db.facades.documents_facade import DocumentsFacade
from shared_libs.services.db.facades.transfer_facade import CollectionTransferFacade


def _s3() -> tuple[MagicMock, object]:
    """An S3 handle whose ``client()`` yields a known raw client; returns (handle, that client)."""
    raw_client = object()

    @asynccontextmanager
    async def _client():
        yield raw_client

    s3 = MagicMock()
    s3.client = _client
    s3.bucket = "bucket"
    return s3, raw_client


async def test_read_source_bytes_gets_the_object_keyed_by_the_source_hash(monkeypatch) -> None:
    s3, raw_client = _s3()
    get = AsyncMock(return_value=b"original")
    monkeypatch.setattr(documents_module.S3ObjectApi, "get", get)

    result = await DocumentsFacade(MagicMock(), MagicMock(), s3).read_source_bytes("sha256-abc")

    assert result == b"original"
    get.assert_awaited_once_with(raw_client, "bucket", "sha256-abc")


async def test_publish_bundle_puts_the_archive_file_and_returns_its_size(monkeypatch) -> None:
    s3, raw_client = _s3()
    put_file = AsyncMock(return_value=4242)
    monkeypatch.setattr(transfer_module.S3ObjectApi, "put_file", put_file)
    archive = pathlib.Path("/tmp/x.dcexport")

    size = await CollectionTransferFacade(MagicMock(), MagicMock(), s3).publish_bundle(
        "col-exports/x.dcexport", archive, "application/x-dcexport"
    )

    assert size == 4242
    put_file.assert_awaited_once_with(
        raw_client, "bucket", "col-exports/x.dcexport", archive, "application/x-dcexport"
    )


async def test_download_bundle_streams_the_object_to_the_local_path(monkeypatch) -> None:
    s3, raw_client = _s3()
    download_to = AsyncMock()
    monkeypatch.setattr(transfer_module.S3ObjectApi, "download_to", download_to)
    target = pathlib.Path("/tmp/bundle.dcexport")

    await CollectionTransferFacade(MagicMock(), MagicMock(), s3).download_bundle(
        "col-exports/x.dcexport", target
    )

    download_to.assert_awaited_once_with(raw_client, "bucket", "col-exports/x.dcexport", target)


async def test_delete_bundle_deletes_the_object_and_propagates_failures(monkeypatch) -> None:
    import pytest  # noqa: PLC0415

    s3, raw_client = _s3()
    delete = AsyncMock()
    monkeypatch.setattr(transfer_module.S3ObjectApi, "delete", delete)
    facade = CollectionTransferFacade(MagicMock(), MagicMock(), s3)

    await facade.delete_bundle("col-exports/x.dcexport")
    delete.assert_awaited_once_with(raw_client, "bucket", "col-exports/x.dcexport")

    # The façade does not swallow: the import task owns the best-effort policy.
    delete.side_effect = RuntimeError("s3 down")
    with pytest.raises(RuntimeError):
        await facade.delete_bundle("col-exports/x.dcexport")


async def test_stage_bundle_puts_the_spooled_upload_and_returns_its_size(monkeypatch) -> None:
    s3, raw_client = _s3()
    put_file = AsyncMock(return_value=77)
    monkeypatch.setattr(transfer_module.S3ObjectApi, "put_file", put_file)
    spooled = pathlib.Path("/tmp/upload.dcexport")

    size = await CollectionTransferFacade(MagicMock(), MagicMock(), s3).stage_bundle(
        "col-imports/x.dcexport", spooled, "application/x-dcexport"
    )

    assert size == 77
    put_file.assert_awaited_once_with(
        raw_client, "bucket", "col-imports/x.dcexport", spooled, "application/x-dcexport"
    )
