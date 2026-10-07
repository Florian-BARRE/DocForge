"""Collection transfer carries the agent-UX schema settings: each metadata field's ``description`` and
the collection's ``title_field`` survive an export → import round trip, a bundle exported BEFORE
either existed still imports (both default to NULL), and a bundle whose title_field names no restored
document-scope field has it dropped to NULL (the uniform dangling-reference policy)."""

from collection_transfer import BundleReader, CollectionExporter
from collection_transfer.manifest import CollectionContractModel
from collection_transfer.restore import CollectionImporterV1, RowDeserializer

from shared_libs.public_models import FieldScope

from .conftest import (
    COLLECTION_ID,
    FakeExportFacade,
    FakeImportFacade,
    make_collection,
    make_schema,
)


class _DescribedExportFacade(FakeExportFacade):
    """The stock fake collection, with a title_field and a described document-scope field."""

    async def get_collection(self, _collection_id):
        collection = make_collection()
        collection.title_field = "author"
        return collection

    async def get_schema(self, _collection_id):
        schema = make_schema()
        schema[0].description = "Who wrote the document"
        return schema


# A metadata_field row exactly as a pre-description bundle wrote it (no "description" key).
_LEGACY_FIELD_ROW = {
    "field_name": "author",
    "field_type": "string",
    "required": False,
    "filterable": True,
    "lexical": False,
    "semantic": False,
    "enum_values": None,
    "origin": "user",
    "scope": "document",
}


def test_legacy_field_row_without_description_imports_as_null() -> None:
    field = RowDeserializer.metadata_field(dict(_LEGACY_FIELD_ROW))
    assert field.field_name == "author"
    assert field.description is None


def test_field_row_description_is_restored_nul_stripped() -> None:
    field = RowDeserializer.metadata_field({**_LEGACY_FIELD_ROW, "description": "Wr\x00iter"})
    assert field.description == "Writer"


def test_legacy_collection_json_without_title_field_defaults_to_null() -> None:
    contract = CollectionContractModel.model_validate(
        {"name": "c", "supported_formats": ["pdf"], "max_file_size_bytes": 1024}
    )
    assert contract.title_field is None


def test_dangling_bundle_title_field_is_dropped_to_null() -> None:
    fields = [RowDeserializer.metadata_field(dict(_LEGACY_FIELD_ROW))]
    assert CollectionImporterV1._restorable_title_field("missing", fields) is None
    assert CollectionImporterV1._restorable_title_field("author", fields) == "author"
    assert CollectionImporterV1._restorable_title_field(None, fields) is None


def test_chunk_scope_bundle_title_field_is_dropped_to_null() -> None:
    row = {**_LEGACY_FIELD_ROW, "origin": "generated", "scope": FieldScope.CHUNK.value}
    fields = [RowDeserializer.metadata_field(row)]
    assert CollectionImporterV1._restorable_title_field("author", fields) is None


async def test_round_trip_carries_description_and_title_field(tmp_path) -> None:
    exporter = CollectionExporter(
        _DescribedExportFacade(), docforge_version="test", created_at="2026-01-01T00:00:00+00:00"
    )
    await exporter.build(COLLECTION_ID, tmp_path / "bundle")
    reader = BundleReader(tmp_path / "bundle")
    reader.validate()
    assert reader.read_collection().title_field == "author"

    facade = FakeImportFacade()
    await CollectionImporterV1(facade, reader).run()

    assert facade.created.title_field == "author"
    by_name = {field.field_name: field for field in facade._fields}
    assert by_name["author"].description == "Who wrote the document"
    assert by_name["topic"].description is None
