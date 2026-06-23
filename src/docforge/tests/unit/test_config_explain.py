# ====== Code Summary ======
# Unit tests for ConfigExplainer — the transparency envelope (provided/defaulted, pipeline
# provenance, metadata accounting, overrides, warnings, needs_reindex notes).

from libs.config.validation import ConfigExplainer


def _doc(metadata_fields: list[dict] | None = None) -> dict:
    return {
        "supported_formats": ["pdf"],
        "pipeline": {},
        "metadata_fields": metadata_fields if metadata_fields is not None else [
            {"field_name": "filename", "is_system": True},
            {"field_name": "language", "is_system": True},
            {"field_name": "project_code", "is_system": False},
        ],
    }


class TestConfigExplainer:
    def test_provided_vs_defaulted(self) -> None:
        applied = ConfigExplainer.build(
            provided_keys={"pipeline", "metadata_fields"},
            raw_pipeline={"chunk": {}},
            resolved_doc=_doc(),
            issues=[],
            needs_reindex=False,
        )
        assert "pipeline" in applied.provided
        assert "metadata_fields" in applied.provided
        assert "embedding_model" in applied.defaulted
        assert "locality_policy" in applied.defaulted

    def test_pipeline_section_provenance(self) -> None:
        applied = ConfigExplainer.build(
            provided_keys={"pipeline"},
            raw_pipeline={"chunk": {"split_method": {"id": "semantic"}}, "enrich": {"enabled": True}},
            resolved_doc=_doc(),
            issues=[],
            needs_reindex=False,
        )
        assert applied.pipeline == {
            "parse": "default", "enrich": "provided", "chunk": "provided", "embed": "default"
        }

    def test_metadata_counts_and_overrides(self) -> None:
        applied = ConfigExplainer.build(
            provided_keys={"metadata_fields"},
            raw_pipeline=None,
            resolved_doc=_doc(),
            issues=[],
            needs_reindex=False,
            custom_field_names=["project_code", "language"],  # language matches a system field
        )
        assert applied.metadata_fields == {"system": 2, "custom": 1}
        assert applied.overridden_system_fields == ["language"]

    def test_warnings_surfaced(self) -> None:
        issues = [
            {"code": "embed.unavailable", "severity": "warning", "field": "embed", "message": "TEI down"},
            {"code": "x.bad", "severity": "error", "field": "x", "message": "blocked"},  # errors excluded
        ]
        applied = ConfigExplainer.build(
            provided_keys=set(), raw_pipeline=None, resolved_doc=_doc(),
            issues=issues, needs_reindex=False,
        )
        assert len(applied.warnings) == 1
        assert applied.warnings[0].code == "embed.unavailable"

    def test_needs_reindex_note(self) -> None:
        applied = ConfigExplainer.build(
            provided_keys={"embedding_model"}, raw_pipeline=None, resolved_doc=_doc(),
            issues=[], needs_reindex=True,
            reindex_reasons=["Modèle d'embedding modifié (a -> b)"],
        )
        assert applied.needs_reindex is True
        assert applied.reindex_reasons == ["Modèle d'embedding modifié (a -> b)"]
        # The note surfaces the reindex cause.
        assert any("Réindexation requise" in n for n in applied.notes)
        assert any("embedding" in n for n in applied.notes)
