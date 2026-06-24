# ====== Code Summary ======
# Unit tests for ConfigRepoHelpers.reindex_diff — the classifier that decides whether a
# config change invalidates already-indexed documents (and explains exactly why).
# Critical: embedding model, indexing pipeline (all sections except query-time `search`),
# searchable metadata schema. Non-critical: search config, non-searchable metadata.

from common_libs.storage.postgres.repositories.config_repo_helpers import ConfigRepoHelpers


def _diff(old_pipe, new_pipe, old_fields, new_fields, oem="bge-m3", nem="bge-m3"):
    """Thin wrapper over reindex_diff for terse test calls."""
    return ConfigRepoHelpers.reindex_diff(
        old_embedding_model=oem, new_embedding_model=nem,
        old_pipeline=old_pipe, new_pipeline=new_pipe,
        old_fields=old_fields, new_fields=new_fields,
    )


class TestReindexDiffNonCritical:
    """Non-critical changes must NOT flag a reindex (documents stay fresh)."""

    def test_search_config_change_is_non_critical(self) -> None:
        relevant, reasons = _diff(
            {"chunk": {"a": 1}, "search": {"retrieve": {"rrf_k": 60}}},
            {"chunk": {"a": 1}, "search": {"retrieve": {"rrf_k": 30}}},
            [], [],
        )
        assert relevant is False
        assert reasons == []

    def test_add_non_searchable_field_is_non_critical(self) -> None:
        old = [{"field_name": "a", "semantic": False, "lexical": False}]
        new = old + [{"field_name": "note", "semantic": False, "lexical": False, "filterable": True}]
        relevant, reasons = _diff({}, {}, old, new)
        assert relevant is False
        assert reasons == []

    def test_remove_non_searchable_field_is_non_critical(self) -> None:
        old = [{"field_name": "a", "semantic": False, "lexical": False},
               {"field_name": "note", "semantic": False, "lexical": False}]
        new = [{"field_name": "a", "semantic": False, "lexical": False}]
        relevant, _ = _diff({}, {}, old, new)
        assert relevant is False

    def test_no_change_is_non_critical(self) -> None:
        relevant, reasons = _diff({"chunk": {"a": 1}}, {"chunk": {"a": 1}}, [], [])
        assert relevant is False and reasons == []


class TestReindexDiffCritical:
    """Index-invalidating changes must flag a reindex and name the exact cause."""

    def test_embedding_model_change(self) -> None:
        relevant, reasons = _diff({}, {}, [], [], oem="bge-m3", nem="openai")
        assert relevant is True
        assert any("embedding" in r.lower() for r in reasons)

    def test_indexing_pipeline_change_names_the_stage(self) -> None:
        relevant, reasons = _diff(
            {"chunk": {"size": 1}, "search": {}},
            {"chunk": {"size": 2}, "search": {}},
            [], [],
        )
        assert relevant is True
        assert any("chunk" in r for r in reasons)

    def test_add_searchable_field(self) -> None:
        old = [{"field_name": "a", "semantic": False, "lexical": False}]
        new = old + [{"field_name": "auteur", "semantic": True, "lexical": False}]
        relevant, reasons = _diff({}, {}, old, new)
        assert relevant is True
        assert any("auteur" in r for r in reasons)

    def test_toggle_field_to_searchable(self) -> None:
        old = [{"field_name": "titre", "semantic": False, "lexical": False}]
        new = [{"field_name": "titre", "semantic": True, "lexical": False}]
        relevant, reasons = _diff({}, {}, old, new)
        assert relevant is True
        assert any("titre" in r for r in reasons)

    def test_remove_searchable_field(self) -> None:
        old = [{"field_name": "x", "semantic": True, "lexical": False}]
        relevant, reasons = _diff({}, {}, old, [])
        assert relevant is True
        assert any("x" in r for r in reasons)

    def test_multiple_causes_reported(self) -> None:
        old = [{"field_name": "a", "semantic": False, "lexical": False}]
        new = old + [{"field_name": "kw", "semantic": False, "lexical": True}]
        relevant, reasons = _diff(
            {"parse": {"x": 1}}, {"parse": {"x": 2}}, old, new, oem="bge", nem="openai",
        )
        assert relevant is True
        # embedding + parse + searchable field → at least three distinct reasons
        assert len(reasons) >= 3
