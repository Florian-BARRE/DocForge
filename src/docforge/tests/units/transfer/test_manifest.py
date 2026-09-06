"""ExportManifest / CollectionContractModel: strict (extra=forbid) validation, JSON round-trip, and
the format-version dispatch seam (is_supported_version + get_importer)."""

import pytest
from collection_transfer import (
    CURRENT_FORMAT_VERSION,
    CollectionContractModel,
    ExportManifest,
    is_supported_version,
)
from collection_transfer.manifest import CollectionRef, TransferCounts
from collection_transfer.restore import (
    CollectionImportError,
    CollectionImporterV1,
    get_importer,
)
from pydantic import ValidationError


def _manifest() -> ExportManifest:
    return ExportManifest(
        format_version=CURRENT_FORMAT_VERSION,
        docforge_version="test",
        created_at="2026-01-01T00:00:00+00:00",
        collection=CollectionRef(id="c", name="n"),
        dense_dim=1024,
        counts=TransferCounts(documents=3, chunks=9, points=9, blobs=4),
    )


def test_manifest_json_round_trip_is_lossless() -> None:
    original = _manifest()
    restored = ExportManifest.model_validate_json(original.model_dump_json())
    assert restored == original
    assert restored.dense_dim == 1024
    assert restored.counts.chunks == 9


def test_manifest_rejects_unknown_key() -> None:
    payload = _manifest().model_dump()
    payload["sneaky"] = True
    with pytest.raises(ValidationError):
        ExportManifest.model_validate(payload)


def test_collection_contract_rejects_unknown_key() -> None:
    with pytest.raises(ValidationError):
        CollectionContractModel.model_validate(
            {"name": "n", "supported_formats": ["pdf"], "max_file_size_bytes": 1, "rogue": 1}
        )


def test_collection_contract_tolerates_legacy_bundle_without_tags() -> None:
    """A bundle exported before ``tags`` existed omits the key entirely — it must import cleanly and
    default to an empty (untagged) list, never a KeyError (the transfer coupling-map tolerance)."""
    contract = CollectionContractModel.model_validate(
        {"name": "n", "supported_formats": ["pdf"], "max_file_size_bytes": 1}
    )
    assert contract.tags == []


def test_collection_contract_round_trips_tags() -> None:
    """A current bundle carries its labels through the JSON round-trip verbatim."""
    original = CollectionContractModel(
        name="n", supported_formats=["pdf"], max_file_size_bytes=1, tags=["legal", "demo"]
    )
    restored = CollectionContractModel.model_validate_json(original.model_dump_json())
    assert restored.tags == ["legal", "demo"]


def test_is_supported_version_gates_on_v1() -> None:
    assert is_supported_version(1) is True
    assert is_supported_version(2) is False


def test_get_importer_dispatches_v1() -> None:
    importer = get_importer(1, facade=object(), reader=object())
    assert isinstance(importer, CollectionImporterV1)


def test_get_importer_rejects_unknown_version() -> None:
    with pytest.raises(CollectionImportError):
        get_importer(99, facade=object(), reader=object())
