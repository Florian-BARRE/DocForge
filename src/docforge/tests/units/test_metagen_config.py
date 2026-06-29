# ====== Code Summary ======
# Unit tests for MetaGenConfig and MetaGenTarget — the S5b pipeline config models.
# Covers: field validation, scope defaults, empty config = no-op, chain coercion from dicts,
# and gate default (failure_policy="continue").

import pytest
from pydantic import ValidationError

from common_libs.config.pipeline.stages.metagen_config import MetaGenConfig, MetaGenTarget


class TestMetaGenTarget:
    """MetaGenTarget — field + prompt + scope validation."""

    def test_minimal_target_requires_field(self) -> None:
        """A target with only 'field' is valid; prompt and scope use defaults."""
        t = MetaGenTarget(field="keywords")
        assert t.field == "keywords"
        assert t.prompt == ""
        assert t.scope == "chunk"

    def test_field_cannot_be_empty(self) -> None:
        """An empty 'field' fails Pydantic min_length validation."""
        with pytest.raises(ValidationError):
            MetaGenTarget(field="")

    def test_document_scope_accepted(self) -> None:
        """scope='document' is a valid Literal value."""
        t = MetaGenTarget(field="summary", scope="document")
        assert t.scope == "document"

    def test_chunk_scope_is_default(self) -> None:
        """When scope is omitted it defaults to 'chunk'."""
        t = MetaGenTarget(field="entity")
        assert t.scope == "chunk"

    def test_invalid_scope_rejected(self) -> None:
        """An unsupported scope literal is rejected by Pydantic."""
        with pytest.raises(ValidationError):
            MetaGenTarget(field="x", scope="paragraph")

    def test_prompt_stored_verbatim(self) -> None:
        """The prompt string is kept as-is (no trimming by the model)."""
        t = MetaGenTarget(field="x", prompt="  Extract entities.  ")
        assert t.prompt == "  Extract entities.  "


class TestMetaGenConfigDefaults:
    """MetaGenConfig — default values produce a no-op stage."""

    def test_empty_config_has_no_targets(self) -> None:
        """A default-constructed MetaGenConfig has an empty targets list."""
        cfg = MetaGenConfig()
        assert cfg.targets == []

    def test_empty_config_has_no_chain(self) -> None:
        """A default-constructed MetaGenConfig has an empty chain list."""
        cfg = MetaGenConfig()
        assert cfg.chain == []

    def test_default_gate_is_continue(self) -> None:
        """The default gate policy is 'continue' (degrade, never fail the document)."""
        cfg = MetaGenConfig()
        assert cfg.gate.failure_policy == "continue"

    def test_default_max_concurrency(self) -> None:
        """Default max_concurrency is 8."""
        cfg = MetaGenConfig()
        assert cfg.max_concurrency == 8

    def test_max_concurrency_clipped_at_1(self) -> None:
        """max_concurrency must be at least 1."""
        with pytest.raises(ValidationError):
            MetaGenConfig(max_concurrency=0)

    def test_max_concurrency_clipped_at_64(self) -> None:
        """max_concurrency must not exceed 64."""
        with pytest.raises(ValidationError):
            MetaGenConfig(max_concurrency=65)


class TestMetaGenConfigWithTargets:
    """MetaGenConfig — populated targets are validated + stored correctly."""

    def test_targets_stored(self) -> None:
        """targets list is preserved exactly."""
        cfg = MetaGenConfig(targets=[
            MetaGenTarget(field="kw", prompt="Get keywords.", scope="chunk"),
            MetaGenTarget(field="summary", scope="document"),
        ])
        assert len(cfg.targets) == 2
        assert cfg.targets[0].field == "kw"
        assert cfg.targets[1].scope == "document"

    def test_empty_targets_is_noop(self) -> None:
        """An explicit empty targets list is still treated as no-op (equivalent to default)."""
        cfg = MetaGenConfig(targets=[])
        assert cfg.targets == []


class TestMetaGenConfigChainCoercion:
    """MetaGenConfig — the @model_validator coerces dicts through the LLM union."""

    def test_already_typed_chain_items_pass_through(self) -> None:
        """Items that are already model instances are left untouched (no double-validation)."""
        from common_libs.providers.llm.openai_compat.config import OpenAICompatLLMConfig
        spec = OpenAICompatLLMConfig(
            id="openai_compat",
            base_url="http://localhost:8080",
            locality="local",
            api_key="local",
            model="llama3",
        )
        cfg = MetaGenConfig(chain=[spec])
        assert cfg.chain[0] is spec

    def test_dict_chain_item_coerced_to_openai_compat(self) -> None:
        """A raw-dict chain entry (round-tripped from DB JSON) is coerced into the config model."""
        raw = {
            "id": "openai_compat",
            "base_url": "http://localhost:8080",
            "locality": "local",
            "api_key": "local",
            "model": "llama3",
        }
        cfg = MetaGenConfig(chain=[raw])
        from common_libs.providers.llm.openai_compat.config import OpenAICompatLLMConfig
        assert isinstance(cfg.chain[0], OpenAICompatLLMConfig)
        assert cfg.chain[0].model == "llama3"

    def test_invalid_dict_in_chain_raises(self) -> None:
        """A dict with an unrecognised LLM id raises ValidationError during coercion."""
        with pytest.raises((ValidationError, Exception)):
            MetaGenConfig(chain=[{"id": "unknown_llm_provider", "base_url": "http://x"}])

    def test_empty_chain_skips_coercion(self) -> None:
        """An empty chain list does not trigger the coercion path (no-op guard)."""
        cfg = MetaGenConfig(chain=[])
        assert cfg.chain == []
