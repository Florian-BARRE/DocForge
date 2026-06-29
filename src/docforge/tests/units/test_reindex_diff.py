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


class TestReindexDiffFailurePolicy:
    """Gate failure-policy vs threshold reindex nuance (CHUNK 2)."""

    def test_failure_policy_change_is_non_critical(self) -> None:
        """Toggling a gate's failure_policy changes run-behavior only → no reindex."""
        relevant, reasons = _diff(
            {"parse": {"gate": {"min_score": 0.5, "failure_policy": "raise"}}},
            {"parse": {"gate": {"min_score": 0.5, "failure_policy": "continue"}}},
            [], [],
        )
        assert relevant is False
        assert reasons == []

    def test_on_degraded_change_is_non_critical(self) -> None:
        """Toggling on_degraded (empty <-> best_effort) → no reindex."""
        relevant, _ = _diff(
            {"enrich": {"ocr_gate": {"min_score": 0.85, "on_degraded": "empty"}}},
            {"enrich": {"ocr_gate": {"min_score": 0.85, "on_degraded": "best_effort"}}},
            [], [],
        )
        assert relevant is False

    def test_min_score_change_on_embed_is_critical(self) -> None:
        """A gate min_score change can change which provider runs → reindex on embed."""
        relevant, reasons = _diff(
            {"embed": {"gate": {"min_score": 0.5, "failure_policy": "raise"}}},
            {"embed": {"gate": {"min_score": 0.8, "failure_policy": "raise"}}},
            [], [],
        )
        assert relevant is True
        assert any("embed" in r for r in reasons)

    def test_max_duration_change_on_parse_is_critical(self) -> None:
        """A gate max_duration_ms change can change which provider is accepted → reindex."""
        relevant, reasons = _diff(
            {"parse": {"gate": {"max_duration_ms": None}}},
            {"parse": {"gate": {"max_duration_ms": 1000}}},
            [], [],
        )
        assert relevant is True
        assert any("parse" in r for r in reasons)

    def test_policy_change_alongside_threshold_change_still_reindexes(self) -> None:
        """A threshold change still flags reindex even when bundled with a policy change."""
        relevant, _ = _diff(
            {"embed": {"gate": {"min_score": 0.5, "failure_policy": "raise"}}},
            {"embed": {"gate": {"min_score": 0.7, "failure_policy": "continue"}}},
            [], [],
        )
        assert relevant is True


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


class TestReindexDiffMetagen:
    """Metagen-specific reindex classification (S5b pipeline.metagen section + generated fields)."""

    def test_metagen_prompt_change_is_critical(self) -> None:
        """Changing a target's prompt changes the LLM output → reindex required.

        pipeline.metagen lives in the non-search pipeline section, so any change triggers
        the stage-level comparison and flags a reindex.
        """
        relevant, reasons = _diff(
            {"metagen": {"targets": [{"field": "kw", "prompt": "Extract keywords.", "scope": "chunk"}]}},
            {"metagen": {"targets": [{"field": "kw", "prompt": "Extract 5 keywords.", "scope": "chunk"}]}},
            [], [],
        )
        assert relevant is True
        assert any("metagen" in r for r in reasons)

    def test_metagen_target_scope_change_is_critical(self) -> None:
        """Changing a target's scope (chunk→document) changes which embedding call is made."""
        relevant, reasons = _diff(
            {"metagen": {"targets": [{"field": "kw", "prompt": "x", "scope": "chunk"}]}},
            {"metagen": {"targets": [{"field": "kw", "prompt": "x", "scope": "document"}]}},
            [], [],
        )
        assert relevant is True
        assert any("metagen" in r for r in reasons)

    def test_metagen_new_target_added_is_critical(self) -> None:
        """Adding a new target generates a field that was previously null → reindex."""
        relevant, reasons = _diff(
            {"metagen": {"targets": [{"field": "kw", "prompt": "x", "scope": "chunk"}]}},
            {"metagen": {"targets": [
                {"field": "kw", "prompt": "x", "scope": "chunk"},
                {"field": "summary", "prompt": "y", "scope": "document"},
            ]}},
            [], [],
        )
        assert relevant is True
        assert any("metagen" in r for r in reasons)

    def test_metagen_chain_provider_change_is_critical(self) -> None:
        """Changing the LLM provider chain changes the generated values → reindex."""
        relevant, _ = _diff(
            {"metagen": {"chain": [{"id": "openai"}]}},
            {"metagen": {"chain": [{"id": "mistral"}]}},
            [], [],
        )
        assert relevant is True

    def test_metagen_no_change_is_non_critical(self) -> None:
        """Identical metagen configs → no reindex."""
        cfg = {"metagen": {"targets": [{"field": "kw", "prompt": "x", "scope": "chunk"}]}}
        relevant, reasons = _diff(cfg, cfg, [], [])
        assert relevant is False
        assert reasons == []

    def test_generated_field_semantic_toggle_is_critical(self) -> None:
        """A generated metadata field gaining semantic=True requires embedding the field → reindex."""
        old = [{"field_name": "kw", "semantic": False, "lexical": False, "origin": "generated"}]
        new = [{"field_name": "kw", "semantic": True, "lexical": False, "origin": "generated"}]
        relevant, reasons = _diff({}, {}, old, new)
        assert relevant is True
        assert any("kw" in r for r in reasons)

    def test_generated_field_lexical_toggle_is_critical(self) -> None:
        """A generated field gaining lexical indexing also requires reindex."""
        old = [{"field_name": "summary", "semantic": False, "lexical": False, "origin": "generated"}]
        new = [{"field_name": "summary", "semantic": False, "lexical": True, "origin": "generated"}]
        relevant, reasons = _diff({}, {}, old, new)
        assert relevant is True
        assert any("summary" in r for r in reasons)

    def test_generated_field_filterable_only_change_is_non_critical(self) -> None:
        """Toggling filterable on a generated field (no searchable vectors) → no reindex."""
        old = [{"field_name": "kw", "semantic": False, "lexical": False, "filterable": False}]
        new = [{"field_name": "kw", "semantic": False, "lexical": False, "filterable": True}]
        relevant, reasons = _diff({}, {}, old, new)
        assert relevant is False
        assert reasons == []

    def test_metagen_failure_policy_change_is_non_critical(self) -> None:
        """Toggling metagen chain failure_policy is non-reindex (run-behavior only)."""
        relevant, _ = _diff(
            {"metagen": {"chain": [{"id": "openai", "gate": {"failure_policy": "raise"}}]}},
            {"metagen": {"chain": [{"id": "openai", "gate": {"failure_policy": "continue"}}]}},
            [], [],
        )
        assert relevant is False
