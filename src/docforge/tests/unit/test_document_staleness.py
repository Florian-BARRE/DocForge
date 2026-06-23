# ====== Code Summary ======
# Unit tests for DocumentStaleness.evaluate — precise, reversible per-document staleness.
# A document is stale only when the index-relevant config it was processed with differs from
# the collection's current config; a reverted change (add then remove a field) leaves it fresh.

import types

from backend.routers.collections.documents.staleness import DocumentStaleness


def _collection(version, *, embedding_model="bge-m3", pipeline=None, fields=None):
    """Build a fake collection ORM stand-in."""
    return types.SimpleNamespace(
        pipeline_version=version,
        embedding_model=embedding_model,
        pipeline=pipeline or {},
        metadata_fields=[types.SimpleNamespace(**f) for f in (fields or [])],
    )


def _snapshot(*, embedding_model="bge-m3", pipeline=None, fields=None):
    """Build a stored config snapshot dict (as persisted in config history)."""
    return {
        "embedding_model": embedding_model,
        "pipeline": pipeline or {},
        "metadata_fields": fields or [],
    }


class TestDocumentStaleness:
    def test_same_version_is_fresh(self) -> None:
        col = _collection("v5")
        stale, reasons = DocumentStaleness.evaluate(col, "v5", {})
        assert stale is False and reasons == []

    def test_search_only_difference_is_fresh(self) -> None:
        # Doc processed at v4 with the same indexing config; only search config changed since.
        col = _collection("v5", pipeline={"chunk": {"a": 1}, "search": {"rrf_k": 30}})
        idx = {"v4": _snapshot(pipeline={"chunk": {"a": 1}, "search": {"rrf_k": 60}})}
        stale, reasons = DocumentStaleness.evaluate(col, "v4", idx)
        assert stale is False and reasons == []

    def test_chunk_change_is_stale_with_reason(self) -> None:
        col = _collection("v5", pipeline={"chunk": {"a": 2}})
        idx = {"v4": _snapshot(pipeline={"chunk": {"a": 1}})}
        stale, reasons = DocumentStaleness.evaluate(col, "v4", idx)
        assert stale is True
        assert any("chunk" in r for r in reasons)

    def test_reverted_field_add_remove_is_fresh(self) -> None:
        # The user's scenario: a field was added then removed. The doc's processing config and
        # the current config are equivalent (no searchable field), even though the version bumped.
        fields = [{"field_name": "a", "semantic": False, "lexical": False}]
        col = _collection("v7", fields=fields)
        idx = {"v4": _snapshot(fields=fields)}  # same searchable schema as now
        stale, reasons = DocumentStaleness.evaluate(col, "v4", idx)
        assert stale is False and reasons == []

    def test_added_searchable_field_is_stale(self) -> None:
        col = _collection("v6", fields=[
            {"field_name": "a", "semantic": False, "lexical": False},
            {"field_name": "auteur", "semantic": True, "lexical": False},
        ])
        idx = {"v4": _snapshot(fields=[{"field_name": "a", "semantic": False, "lexical": False}])}
        stale, reasons = DocumentStaleness.evaluate(col, "v4", idx)
        assert stale is True
        assert any("auteur" in r for r in reasons)

    def test_missing_snapshot_is_conservatively_stale(self) -> None:
        col = _collection("v9")
        stale, reasons = DocumentStaleness.evaluate(col, "v2", {})  # no snapshot for v2
        assert stale is True
        assert reasons  # carries a fallback explanation
