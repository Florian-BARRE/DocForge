# ====== Code Summary ======
# Unit tests for the rerank coherence rule in the config validator:
#   search.rerank.enabled == true with an empty chain is an ERROR-severity issue
#   (so saving such a config returns 422), while enabled + non-empty passes the rule.
# Tests both the focused PipelineChecks.check_step_dependencies and the end-to-end
# ConfigValidator.validate path (the same validator the config update/create route runs).

from common_libs.config.pipeline import PipelineConfig
from common_libs.config.validation import ConfigValidator
from common_libs.config.validation.validator.pipeline_checks import PipelineChecks


# ── Focused rule: PipelineChecks.check_step_dependencies ──────────────────────────


class TestRerankChainRule:
    """search.rerank coherence: enabled requires a configured provider chain."""

    def test_enabled_empty_chain_is_error(self) -> None:
        """rerank enabled with an empty chain → one error-severity issue."""
        pipeline = PipelineConfig.from_dict({"search": {"rerank": {"enabled": True, "chain": []}}})
        issues: list[dict] = []
        PipelineChecks.check_step_dependencies(pipeline, issues)
        errors = [i for i in issues if i["severity"] == "error"]
        assert len(errors) == 1
        assert errors[0]["code"] == "search.rerank.empty_chain"
        assert errors[0]["field"] == "pipeline.search.rerank.chain"

    def test_enabled_non_empty_chain_passes(self) -> None:
        """rerank enabled with a configured provider → no rerank-chain issue."""
        pipeline = PipelineConfig.from_dict({
            "search": {"rerank": {"enabled": True, "chain": [{"id": "bge_server"}]}}
        })
        issues: list[dict] = []
        PipelineChecks.check_step_dependencies(pipeline, issues)
        assert [i for i in issues if i["code"] == "search.rerank.empty_chain"] == []

    def test_disabled_empty_chain_passes(self) -> None:
        """rerank disabled with an empty chain is the default, valid, state."""
        pipeline = PipelineConfig.from_dict({"search": {"rerank": {"enabled": False, "chain": []}}})
        issues: list[dict] = []
        PipelineChecks.check_step_dependencies(pipeline, issues)
        assert [i for i in issues if i["code"] == "search.rerank.empty_chain"] == []


# ── End-to-end: ConfigValidator.validate (the path the API runs) ──────────────────


def _doc(pipeline: dict) -> dict:
    """Build a minimal valid config document carrying the given pipeline block."""
    return {
        "locality_policy": "external_allowed",
        "embedding_model": "BAAI/bge-m3",
        "pipeline": pipeline,
        "metadata_fields": [],
    }


class TestConfigValidatorRerank:
    """ConfigValidator surfaces the rerank-chain rule as an error so the API returns 422."""

    def test_validate_rejects_enabled_empty_chain(self) -> None:
        """An enabled+empty rerank chain yields an error issue (→ 422 at the route)."""
        doc = _doc({"search": {"rerank": {"enabled": True, "chain": []}}})
        # Empty stages: the empty chain means there is no provider to look up in the index,
        # so the rerank-chain rule is what flags the config.
        issues = ConfigValidator.validate(doc, stages=[])
        errors = [i for i in issues if i["severity"] == "error"]
        assert any(i["code"] == "search.rerank.empty_chain" for i in errors)
