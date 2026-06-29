# ====== Code Summary ======
# Unit tests for MetagenChecks.check_metagen — static validator for the S5b metagen config block.
# Covers all issue codes (errors): metagen.target_missing_field, target_unknown_field,
# target_not_generated, duplicate_target, bad_scope, no_provider; and (warnings):
# metagen.empty_prompt, orphan_field. Signature: check_metagen(doc: dict, issues: list).

import pytest

from common_libs.config.validation.validator.metagen_checks import MetagenChecks


# ─── Helpers ────────────────────────────────────────────────────────────────────

def _doc(
    targets: list[dict] | None = None,
    chain: list | None = None,
    fields: list[dict] | None = None,
) -> dict:
    """
    Build a minimal canonical config document for MetagenChecks.check_metagen.

    Args:
        targets: pipeline.metagen.targets entries.
        chain: pipeline.metagen.chain entries (non-empty = provider configured).
        fields: metadata_fields entries (each should have field_name + origin).
    """
    return {
        "pipeline": {
            "metagen": {
                "targets": targets or [],
                "chain": chain or [],
            }
        },
        "metadata_fields": fields or [],
    }


def _field(name: str, origin: str = "user") -> dict:
    """Build a metadata_fields entry."""
    return {"field_name": name, "origin": origin}


def _target(field: str, scope: str = "chunk", prompt: str = "Extract.") -> dict:
    """Build a pipeline.metagen.targets entry."""
    return {"field": field, "scope": scope, "prompt": prompt}


def _codes(issues: list[dict]) -> list[str]:
    """Extract just the issue codes from an issues list."""
    return [i["code"] for i in issues]


def _severities(issues: list[dict]) -> list[str]:
    return [i["severity"] for i in issues]


class TestMetagenChecksInstantiation:
    """MetagenChecks is static-only; instantiation must be blocked."""

    def test_cannot_instantiate(self) -> None:
        with pytest.raises(TypeError):
            MetagenChecks()  # type: ignore[call-arg]


class TestNoIssues:
    """A valid metagen config produces no issues."""

    def test_clean_config_no_issues(self) -> None:
        """A target binding a generated field with a provider → zero issues."""
        issues: list[dict] = []
        MetagenChecks.check_metagen(
            _doc(
                targets=[_target("kw")],
                chain=[{"id": "openai_compat"}],
                fields=[_field("kw", "generated")],
            ),
            issues,
        )
        assert issues == []

    def test_empty_config_no_issues(self) -> None:
        """An entirely empty metagen block (no targets, no chain) → zero issues."""
        issues: list[dict] = []
        MetagenChecks.check_metagen(_doc(), issues)
        assert issues == []

    def test_multiple_valid_targets(self) -> None:
        """Multiple distinct targets each binding a different generated field → no issues."""
        issues: list[dict] = []
        MetagenChecks.check_metagen(
            _doc(
                targets=[_target("kw"), _target("summary", scope="document")],
                chain=[{"id": "openai_compat"}],
                fields=[_field("kw", "generated"), _field("summary", "generated")],
            ),
            issues,
        )
        assert issues == []


# ─── Error codes ───────────────────────────────────────────────────────────────

class TestTargetMissingField:
    """metagen.target_missing_field — a target with a blank/missing 'field'."""

    def test_blank_field_name(self) -> None:
        issues: list[dict] = []
        MetagenChecks.check_metagen(
            _doc(
                targets=[{"field": "", "scope": "chunk", "prompt": "Do it."}],
                chain=[{"id": "openai_compat"}],
                fields=[],
            ),
            issues,
        )
        assert "metagen.target_missing_field" in _codes(issues)
        assert "error" in _severities(issues)

    def test_missing_field_key(self) -> None:
        """A target dict without a 'field' key at all is treated as blank."""
        issues: list[dict] = []
        MetagenChecks.check_metagen(
            _doc(
                targets=[{"scope": "chunk", "prompt": "x"}],
                chain=[{"id": "openai_compat"}],
            ),
            issues,
        )
        assert "metagen.target_missing_field" in _codes(issues)


class TestTargetUnknownField:
    """metagen.target_unknown_field — field does not exist in the metadata schema at all."""

    def test_field_not_in_schema(self) -> None:
        issues: list[dict] = []
        MetagenChecks.check_metagen(
            _doc(
                targets=[_target("ghost_field")],
                chain=[{"id": "openai_compat"}],
                fields=[_field("kw", "generated")],  # 'ghost_field' not here
            ),
            issues,
        )
        assert "metagen.target_unknown_field" in _codes(issues)
        err = next(i for i in issues if i["code"] == "metagen.target_unknown_field")
        assert "ghost_field" in err["message"]

    def test_error_severity(self) -> None:
        issues: list[dict] = []
        MetagenChecks.check_metagen(
            _doc(targets=[_target("absent")], chain=[{"id": "p"}], fields=[]),
            issues,
        )
        err = next(i for i in issues if i["code"] == "metagen.target_unknown_field")
        assert err["severity"] == "error"


class TestTargetNotGenerated:
    """metagen.target_not_generated — field exists but has origin != 'generated'."""

    def test_user_field_cannot_be_target(self) -> None:
        issues: list[dict] = []
        MetagenChecks.check_metagen(
            _doc(
                targets=[_target("author")],
                chain=[{"id": "openai_compat"}],
                fields=[_field("author", "user")],  # origin=user, not generated
            ),
            issues,
        )
        assert "metagen.target_not_generated" in _codes(issues)
        err = next(i for i in issues if i["code"] == "metagen.target_not_generated")
        assert "author" in err["message"]
        assert err["severity"] == "error"

    def test_system_field_cannot_be_target(self) -> None:
        issues: list[dict] = []
        MetagenChecks.check_metagen(
            _doc(
                targets=[_target("filename")],
                chain=[{"id": "openai_compat"}],
                fields=[_field("filename", "system")],
            ),
            issues,
        )
        assert "metagen.target_not_generated" in _codes(issues)


class TestDuplicateTarget:
    """metagen.duplicate_target — two targets bind the same field name."""

    def test_duplicate_field_name(self) -> None:
        issues: list[dict] = []
        MetagenChecks.check_metagen(
            _doc(
                targets=[_target("kw"), _target("kw")],
                chain=[{"id": "openai_compat"}],
                fields=[_field("kw", "generated")],
            ),
            issues,
        )
        assert "metagen.duplicate_target" in _codes(issues)
        dup = next(i for i in issues if i["code"] == "metagen.duplicate_target")
        assert dup["severity"] == "error"
        assert "kw" in dup["message"]

    def test_third_duplicate_also_reported(self) -> None:
        """Each occurrence after the first is reported as a duplicate."""
        issues: list[dict] = []
        MetagenChecks.check_metagen(
            _doc(
                targets=[_target("kw"), _target("kw"), _target("kw")],
                chain=[{"id": "p"}],
                fields=[_field("kw", "generated")],
            ),
            issues,
        )
        dup_codes = [i for i in issues if i["code"] == "metagen.duplicate_target"]
        # Two duplicates (occurrences 2 and 3 are each flagged)
        assert len(dup_codes) >= 1


class TestBadScope:
    """metagen.bad_scope — scope is not one of the allowed values."""

    def test_invalid_scope_string(self) -> None:
        issues: list[dict] = []
        MetagenChecks.check_metagen(
            _doc(
                targets=[{"field": "kw", "scope": "paragraph", "prompt": "X"}],
                chain=[{"id": "openai_compat"}],
                fields=[_field("kw", "generated")],
            ),
            issues,
        )
        assert "metagen.bad_scope" in _codes(issues)
        bad = next(i for i in issues if i["code"] == "metagen.bad_scope")
        assert bad["severity"] == "error"
        assert "paragraph" in bad["message"]


class TestNoProvider:
    """metagen.no_provider — targets configured but no LLM chain entry."""

    def test_targets_without_chain_is_error(self) -> None:
        issues: list[dict] = []
        MetagenChecks.check_metagen(
            _doc(
                targets=[_target("kw")],
                chain=[],  # no provider
                fields=[_field("kw", "generated")],
            ),
            issues,
        )
        assert "metagen.no_provider" in _codes(issues)
        no_prov = next(i for i in issues if i["code"] == "metagen.no_provider")
        assert no_prov["severity"] == "error"
        assert no_prov["field"] == "pipeline.metagen.chain"

    def test_no_targets_no_chain_is_fine(self) -> None:
        """No targets + no chain = empty config = no issue (the no-op case)."""
        issues: list[dict] = []
        MetagenChecks.check_metagen(_doc(targets=[], chain=[]), issues)
        assert "metagen.no_provider" not in _codes(issues)


# ─── Warning codes ─────────────────────────────────────────────────────────────

class TestEmptyPrompt:
    """metagen.empty_prompt — a target with a blank prompt (advisory warning, still runs)."""

    def test_blank_prompt_is_warning(self) -> None:
        issues: list[dict] = []
        MetagenChecks.check_metagen(
            _doc(
                targets=[{"field": "kw", "scope": "chunk", "prompt": ""}],
                chain=[{"id": "openai_compat"}],
                fields=[_field("kw", "generated")],
            ),
            issues,
        )
        assert "metagen.empty_prompt" in _codes(issues)
        warn = next(i for i in issues if i["code"] == "metagen.empty_prompt")
        assert warn["severity"] == "warning"

    def test_whitespace_only_prompt_is_warning(self) -> None:
        """A prompt with only whitespace is treated as blank."""
        issues: list[dict] = []
        MetagenChecks.check_metagen(
            _doc(
                targets=[{"field": "kw", "scope": "chunk", "prompt": "   \t  "}],
                chain=[{"id": "openai_compat"}],
                fields=[_field("kw", "generated")],
            ),
            issues,
        )
        assert "metagen.empty_prompt" in _codes(issues)

    def test_non_empty_prompt_no_warning(self) -> None:
        """A non-blank prompt produces no empty_prompt issue."""
        issues: list[dict] = []
        MetagenChecks.check_metagen(
            _doc(
                targets=[_target("kw", prompt="Extract keywords.")],
                chain=[{"id": "openai_compat"}],
                fields=[_field("kw", "generated")],
            ),
            issues,
        )
        assert "metagen.empty_prompt" not in _codes(issues)


class TestOrphanField:
    """metagen.orphan_field — a generated field with no bound metagen target."""

    def test_generated_field_without_target_warns(self) -> None:
        """A generated metadata_field with no matching target → orphan warning."""
        issues: list[dict] = []
        MetagenChecks.check_metagen(
            _doc(
                targets=[],  # no targets
                chain=[{"id": "openai_compat"}],
                fields=[_field("kw", "generated")],
            ),
            issues,
        )
        assert "metagen.orphan_field" in _codes(issues)
        warn = next(i for i in issues if i["code"] == "metagen.orphan_field")
        assert warn["severity"] == "warning"
        assert "kw" in warn["message"]

    def test_bound_generated_field_no_orphan_warning(self) -> None:
        """A generated field that IS bound to a target produces no orphan warning."""
        issues: list[dict] = []
        MetagenChecks.check_metagen(
            _doc(
                targets=[_target("kw")],
                chain=[{"id": "openai_compat"}],
                fields=[_field("kw", "generated")],
            ),
            issues,
        )
        assert "metagen.orphan_field" not in _codes(issues)

    def test_multiple_orphan_fields_each_warned(self) -> None:
        """Each unbound generated field gets its own orphan warning."""
        issues: list[dict] = []
        MetagenChecks.check_metagen(
            _doc(
                targets=[_target("bound")],
                chain=[{"id": "openai_compat"}],
                fields=[
                    _field("bound", "generated"),
                    _field("orphan_a", "generated"),
                    _field("orphan_b", "generated"),
                ],
            ),
            issues,
        )
        orphan_codes = [i for i in issues if i["code"] == "metagen.orphan_field"]
        assert len(orphan_codes) == 2

    def test_user_fields_not_orphaned(self) -> None:
        """Non-generated fields (user/system) are never reported as orphans."""
        issues: list[dict] = []
        MetagenChecks.check_metagen(
            _doc(
                targets=[],
                chain=[],
                fields=[_field("author", "user"), _field("filename", "system")],
            ),
            issues,
        )
        assert "metagen.orphan_field" not in _codes(issues)


# ─── Issue field paths ─────────────────────────────────────────────────────────

class TestIssueFieldPaths:
    """Issue records carry correct dot-path 'field' values for UI highlighting."""

    def test_no_provider_field_path(self) -> None:
        issues: list[dict] = []
        MetagenChecks.check_metagen(
            _doc(targets=[_target("kw")], fields=[_field("kw", "generated")]),
            issues,
        )
        prov = next(i for i in issues if i["code"] == "metagen.no_provider")
        assert prov["field"] == "pipeline.metagen.chain"

    def test_target_index_in_field_path(self) -> None:
        """The second target's issues carry targets[1] in the field path."""
        issues: list[dict] = []
        MetagenChecks.check_metagen(
            _doc(
                targets=[_target("kw"), _target("ghost")],
                chain=[{"id": "p"}],
                fields=[_field("kw", "generated")],
            ),
            issues,
        )
        ghost_issue = next(
            i for i in issues if i["code"] == "metagen.target_unknown_field"
        )
        assert "targets[1]" in ghost_issue["field"]
