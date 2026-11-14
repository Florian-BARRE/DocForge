"""PreviewSourceResolver depends on the PreviewReadPort, not on the Database (R-15)."""

import uuid
from types import SimpleNamespace

import pytest

from shared_libs.pipelines.preview import PreviewInputError, PreviewSourceResolver


class _Documents:
    def __init__(self, chunks: list[bytes] | None, metadata: list[SimpleNamespace]) -> None:
        self._chunks, self._metadata = chunks, metadata

    async def stream_blob(self, content_hash: str):
        if self._chunks is None:
            return None

        async def _stream():
            for chunk in self._chunks:
                yield chunk

        return _stream(), "application/pdf"

    async def get_metadata(self, document_id: uuid.UUID):
        return self._metadata


class _Collections:
    def __init__(self, schema: list[SimpleNamespace]) -> None:
        self._schema = schema

    async def get_schema(self, collection_id: uuid.UUID):
        return self._schema


def _port(chunks, metadata=(), schema=()) -> SimpleNamespace:
    return SimpleNamespace(
        documents=_Documents(chunks, list(metadata)), collections=_Collections(list(schema))
    )


def _document() -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid.uuid4(), filename="a.pdf", source_hash="h", collection_id=uuid.uuid4()
    )


async def test_rehydrates_bytes_and_user_declared_meta() -> None:
    field_id = uuid.uuid4()
    port = _port(
        [b"ab", b"cd"],
        metadata=[
            SimpleNamespace(field_id=field_id, origin=SimpleNamespace(value="user"), value="x"),
            SimpleNamespace(field_id=field_id, origin=SimpleNamespace(value="llm"), value="y"),
        ],
        schema=[SimpleNamespace(id=field_id, field_name="author")],
    )

    source = await PreviewSourceResolver(port).from_document(_document(), 100)

    assert (source.filename, source.content, source.declared_meta) == (
        "a.pdf",
        b"abcd",
        {"author": "x"},
    )


async def test_missing_bytes_and_oversized_bytes_are_input_errors() -> None:
    with pytest.raises(PreviewInputError, match="no longer in the store"):
        await PreviewSourceResolver(_port(None)).from_document(_document(), 100)
    with pytest.raises(PreviewInputError, match="exceeds the preview size cap"):
        await PreviewSourceResolver(_port([b"abcdef"])).from_document(_document(), 3)
