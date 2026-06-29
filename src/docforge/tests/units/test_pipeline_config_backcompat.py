# ====== Code Summary ======
# Back-compat tests for the PipelineConfig shim (PR-2). The flat fields stay the canonical storage
# shape (so discovery / direct-dict readers are untouched); from_dict additionally accepts the new
# keyed {"stages": {...}, "search": {...}} shape and un-nests it. Covers: empty/None defaults; old
# flat blob and new keyed blob parse to an EQUIVALENT config; the property shims (cfg.parse etc.)
# return the right typed sub-configs; the `stages` keyed-view property; to_dict round-trips.

# ====== Third-Party Library Imports ======
import pytest

# ====== Internal Project Imports ======
from common_libs.config.pipeline import PipelineConfig

_STAGE_KEYS = {"parse", "enrich", "chunk", "contextualize", "metagen", "embed"}


class TestPipelineConfigBackCompat:
    """from_dict reads BOTH the old flat shape and the new keyed shape transparently."""

    def test_empty_and_none_fall_back_to_defaults(self) -> None:
        default_blob = PipelineConfig().to_dict()
        assert PipelineConfig.from_dict(None).to_dict() == default_blob
        assert PipelineConfig.from_dict({}).to_dict() == default_blob

    def test_old_flat_blob_parses(self) -> None:
        # The shape every collection.pipeline is stored as today.
        flat = PipelineConfig().to_dict()
        cfg = PipelineConfig.from_dict(flat)
        assert cfg.to_dict() == flat

    def test_new_keyed_blob_equivalent_to_old_flat(self) -> None:
        base = PipelineConfig()
        flat_blob = base.to_dict()
        keyed_blob = {"stages": base.stages, "search": base.search.model_dump(mode="json")}
        cfg_flat = PipelineConfig.from_dict(flat_blob)
        cfg_keyed = PipelineConfig.from_dict(keyed_blob)
        # Both shapes normalize to the same canonical config.
        assert cfg_keyed.to_dict() == cfg_flat.to_dict()

    def test_non_default_value_round_trips_in_both_shapes(self) -> None:
        flat = {"chunk": {"split_method": {"id": "token_budget", "max_tokens": 999}}}
        keyed = {"stages": {"chunk": {"split_method": {"id": "token_budget", "max_tokens": 999}}}}
        cfg_flat = PipelineConfig.from_dict(flat)
        cfg_keyed = PipelineConfig.from_dict(keyed)
        assert cfg_flat.chunk.split_method.max_tokens == 999
        assert cfg_keyed.chunk.split_method.max_tokens == 999
        assert cfg_flat.to_dict() == cfg_keyed.to_dict()

    def test_property_shims_return_typed_subconfigs(self) -> None:
        cfg = PipelineConfig.from_dict(PipelineConfig().to_dict())
        assert type(cfg.parse).__name__ == "ParseConfig"
        assert type(cfg.enrich).__name__ == "EnrichConfig"
        assert type(cfg.chunk).__name__ == "ChunkConfig"
        assert type(cfg.metagen).__name__ == "MetaGenConfig"
        assert type(cfg.embed).__name__ == "EmbedConfig"
        # The parse gate sub-object resolves through the shim.
        assert cfg.parse.gate is not None

    def test_stages_keyed_view_keys(self) -> None:
        stages = PipelineConfig().stages
        assert set(stages) == _STAGE_KEYS
        # Each entry is the JSON dump of its block (a dict), search is NOT a stage.
        assert all(isinstance(v, dict) for v in stages.values())
        assert "search" not in stages

    def test_to_dict_round_trips(self) -> None:
        cfg = PipelineConfig.from_dict({"chunk": {"split_method": {"id": "token_budget", "max_tokens": 256}}})
        assert PipelineConfig.from_dict(cfg.to_dict()).to_dict() == cfg.to_dict()
