# ====== Code Summary ======
# Shared fixtures for the collection-transfer engine tests: tiny ORM-row builders (constructed
# without a session — SQLAlchemy models are plain attribute holders) and two in-memory fake gateways
# standing in for CollectionTransferFacade. FakeExportFacade feeds the exporter a one-document
# collection (with a blob referenced twice, to exercise dedup); FakeImportFacade records every
# restore call so a test can assert the id-remap, the chunk==point identity kept THROUGH it, and rollback.

# ====== Standard Library Imports ======
import hashlib
import uuid
from types import SimpleNamespace

# ====== Third-Party Library Imports ======
import pytest

# ====== Internal Project Imports ======
from shared_libs.pipelines.ingest import IngestPipeline
from shared_libs.public_models import FieldOrigin, FieldScope, FieldType
from shared_libs.services.db.facades import DocumentExportRows
from shared_libs.services.db.postgresql.tables import (
    Blob,
    BlobKind,
    Block,
    BlockEnrichment,
    Chunk,
    ChunkBlock,
    Collection,
    Document,
    DocumentStatus,
    EnrichmentKind,
    EnrichmentStatus,
    MetadataField,
    Page,
    SourceKind,
)

# Deterministic SOURCE ids so tests can assert the import REMAPS them (new != old) consistently.
COLLECTION_ID = uuid.UUID("0c534a78-6dcc-4ab6-869a-94717be1815c")
DOC_ID = uuid.UUID("11111111-1111-1111-1111-111111111111")
CHUNK_ID = uuid.UUID("22222222-2222-2222-2222-222222222222")
BLOCK_ID = f"{DOC_ID}:#/texts/0"
# Content-addressed: the bundle re-hashes blob bytes on read, so the hash MUST equal sha256(bytes).
ORIGINAL_BYTES = b"AAA"
PDF_BYTES = b"BBB"
ORIGINAL_HASH = hashlib.sha256(ORIGINAL_BYTES).hexdigest()
PDF_HASH = hashlib.sha256(PDF_BYTES).hexdigest()
DENSE_DIM = 4


def make_collection() -> Collection:
    """A minimal source collection row carrying a REAL, buildable pipeline blob.

    The importer now fail-fast validates the bundle's stored graph blobs before any write (exactly
    like every other write boundary), so the fixture must carry a graph that builds + passes the
    structural validator — the stock light ingest pipeline. The search blob stays ``{}`` (the valid
    stock default: "use the built-in search pipeline").
    """
    collection = Collection(
        name="DemoCollection",
        supported_formats=["pdf"],
        max_file_size_bytes=1024,
        needs_reindex=False,
        pipeline=IngestPipeline.light_blob().model_dump(mode="json"),
        search={},
    )
    collection.id = COLLECTION_ID
    collection.job_timeout_seconds = None
    return collection


def make_schema() -> list[MetadataField]:
    """Two fields — a filterable doc-scope and a semantic chunk-scope generated field."""
    author = MetadataField(
        field_name="author",
        field_type=FieldType.STRING,
        required=False,
        filterable=True,
        lexical=False,
        semantic=False,
        enum_values=None,
        origin=FieldOrigin.USER,
        scope=FieldScope.DOCUMENT,
    )
    author.id = 7
    author.collection_id = COLLECTION_ID
    topic = MetadataField(
        field_name="topic",
        field_type=FieldType.STRING,
        required=False,
        filterable=False,
        lexical=False,
        semantic=True,
        enum_values=None,
        origin=FieldOrigin.GENERATED,
        scope=FieldScope.CHUNK,
    )
    topic.id = 9
    topic.collection_id = COLLECTION_ID
    return [author, topic]


def make_document() -> Document:
    """One DONE document referencing an original + a canonical PDF blob."""
    return Document(
        id=DOC_ID,
        collection_id=COLLECTION_ID,
        source_hash=ORIGINAL_HASH,
        pdf_blob_hash=PDF_HASH,
        filename="demo.pdf",
        format="pdf",
        mime_type="application/pdf",
        file_size=512,
        page_count=1,
        language="en",
        source_kind=SourceKind.DIGITAL_BORN,
        title="Demo",
        simhash=None,
        status=DocumentStatus.DONE,
        pipeline_version="v1",
        enabled=True,
    )


def make_document_rows() -> DocumentExportRows:
    """The whole per-document row set the exporter streams (metadata keyed by NAME)."""
    block = Block(
        id=BLOCK_ID,
        document_id=DOC_ID,
        block_type="text",
        page=0,
        bbox=[0.0, 0.0, 1.0, 1.0],
        reading_order=0,
        column_index=0,
        parent_id=None,
        level=None,
        text="Hello world",
        is_boilerplate=False,
        language="en",
        confidence=None,
    )
    enrichment = BlockEnrichment(
        block_id=BLOCK_ID,
        kind=EnrichmentKind.OCR,
        text="ocr",
        data=None,
        status=EnrichmentStatus.OK,
    )
    enrichment.id = uuid.UUID("33333333-3333-3333-3333-333333333333")
    chunk = Chunk(
        id=CHUNK_ID,
        document_id=DOC_ID,
        config_hash="cfg",
        chunk_index=0,
        strategy="fixed",
        parent_id=None,
        text="Hello world",
        token_count=2,
        heading_path=["Intro"],
        simhash=None,
        is_indexed=True,
        role="body",
        enabled_override=None,
    )
    page = Page(
        id=uuid.UUID("44444444-4444-4444-4444-444444444444"),
        document_id=DOC_ID,
        page_number=0,
        width=1.0,
        height=1.0,
        is_scanned=False,
        language="en",
        render_blob_hash=None,
    )
    return DocumentExportRows(
        document=make_document(),
        metadata=[("author", "Ada", FieldOrigin.USER)],
        pages=[page],
        blocks=[block],
        tables=[],
        figures=[],
        enrichments=[enrichment],
        chunks=[chunk],
        composition=[ChunkBlock(chunk_id=CHUNK_ID, block_id=BLOCK_ID, position=0)],
        chunk_metadata=[(CHUNK_ID, "topic", "greetings", FieldOrigin.GENERATED)],
    )


def make_blob_rows() -> list[Blob]:
    """Two registry rows (original + PDF)."""
    return [
        Blob(
            content_hash=ORIGINAL_HASH,
            s3_key=ORIGINAL_HASH,
            mime_type="application/pdf",
            size_bytes=len(ORIGINAL_BYTES),
            kind=BlobKind.ORIGINAL,
        ),
        Blob(
            content_hash=PDF_HASH,
            s3_key=PDF_HASH,
            mime_type="application/pdf",
            size_bytes=len(PDF_BYTES),
            kind=BlobKind.CANONICAL_PDF,
        ),
    ]


def make_point_record() -> SimpleNamespace:
    """A fake Qdrant scroll record: id (= chunk id), one dense + one sparse vector, a payload."""
    return SimpleNamespace(
        id=str(CHUNK_ID),
        vector={
            "content_dense": [0.1, 0.2, 0.3, 0.4],
            "content_bm25": SimpleNamespace(indices=[1, 5], values=[0.7, 0.3]),
        },
        payload={"document_id": str(DOC_ID), "enabled": True, "author": "Ada"},
    )


class FakeExportFacade:
    """In-memory CollectionTransferFacade stand-in for the exporter (reads only)."""

    def __init__(self) -> None:
        self._blob_bytes = {ORIGINAL_HASH: ORIGINAL_BYTES, PDF_HASH: PDF_BYTES}

    async def get_collection(self, _collection_id):
        return make_collection()

    async def get_schema(self, _collection_id):
        return make_schema()

    async def list_config_versions(self, _collection_id):
        return []

    async def dense_dim(self, _collection_id):
        return DENSE_DIM

    async def list_document_ids(self, _collection_id):
        return [DOC_ID]

    async def read_document_export(self, _document_id):
        return make_document_rows()

    async def collect_blob_hashes(self, _collection_id):
        # The same original hash is referenced by two docs in reality; the walker still lists it once.
        return [ORIGINAL_HASH, PDF_HASH]

    async def get_blob_rows(self, _hashes):
        return make_blob_rows()

    async def read_blob_bytes(self, s3_key):
        return self._blob_bytes[s3_key]

    async def scroll_points(self, _collection_id, _batch_size=256):
        yield make_point_record()


class FakeImportFacade:
    """In-memory CollectionTransferFacade stand-in for the importer (records restore calls)."""

    def __init__(self, *, existing_names=(), fail_on=None) -> None:
        self._existing = set(existing_names)
        self._fail_on = fail_on  # a table path whose restore_rows should raise
        self.created: Collection | None = None
        self.restored: dict[str, list] = {}
        self.blob_objects: list = []
        self.blob_rows: list = []
        self.ensured_dense_dim: int | None = None
        self.points: list = []
        self.rolled_back: list = []
        self._new_id = uuid.uuid4()

    async def name_taken(self, name):
        return name in self._existing

    async def create_collection(self, collection, fields):
        collection.id = self._new_id
        for index, field in enumerate(fields):
            field.id = 100 + index  # fresh autoincrement ids, DIFFERENT from the source (7/9)
            field.collection_id = self._new_id
        self.created = collection
        self._fields = fields
        return collection

    async def field_id_map(self, _collection_id):
        return {field.field_name: field.id for field in self._fields}

    async def restore_rows(self, rows):
        rows = list(rows)
        if rows and self._fail_on and rows[0].__class__.__name__ == self._fail_on:
            raise RuntimeError(f"boom restoring {self._fail_on}")
        self.restored.setdefault(rows[0].__class__.__name__ if rows else "empty", []).extend(rows)

    async def store_blobs(self, objects, rows):
        self.blob_objects.extend(objects)
        self.blob_rows.extend(rows)

    async def ensure_vector_space(self, _collection_id, dense_dim):
        self.ensured_dense_dim = dense_dim

    async def upsert_points(self, _collection_id, points):
        self.points.extend(points)

    async def rollback_collection(self, collection_id):
        self.rolled_back.append(collection_id)


@pytest.fixture
def export_facade() -> FakeExportFacade:
    return FakeExportFacade()


@pytest.fixture
def import_facade() -> FakeImportFacade:
    return FakeImportFacade()
