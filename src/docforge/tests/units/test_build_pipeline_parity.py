# ====== Code Summary ======
# Assembler integration gate: build_pipeline(default_config) must yield the canonical stage set +
# order, the right inner stage TYPES wrapped by each adapter, and inner chains/params identical to
# invoking the shared inner builders directly (parse chain, S2/S4 fingerprint params, embed chain) —
# the byte-identical-inner guarantee. Also asserts the embed/index stage is omitted when Qdrant is
# absent. Fully mocked infra (real ProviderRegistry + RUNTIME_CONFIG; MagicMock s3/qdrant/chunk_repo).

# ====== Standard Library Imports ======
from unittest.mock import MagicMock

# ====== Third-Party Library Imports ======
import pytest

# ====== Internal Project Imports ======
from config import RUNTIME_CONFIG
from common_libs.config.pipeline import build_default_pipeline
from common_libs.pipeline.assembly import ProviderRegistry
from common_libs.pipeline.assembly.chunk_stage_assembler import ChunkStageAssembler
from common_libs.pipeline.assembly.stage_assembler import build_pipeline
from common_libs.pipeline.stages.context import StageDeps
from common_libs.pipeline.ingest.stages.ingest import IngestDocStage
from common_libs.pipeline.stages.s1_parse.core import S1ParseStage
from common_libs.pipeline.stages.s2_enrich.core import S2EnrichStage
from common_libs.pipeline.stages.s4_chunk.core import S4ChunkStage
from common_libs.pipeline.stages.s5_contextualize.core import S5ContextualizeStage
from common_libs.pipeline.stages.s5b_metagen.core import S5bMetagenStage
from common_libs.pipeline.stages.s6_embed_index.core import S6EmbedIndexStage

_CANONICAL_ORDER = ["ingest", "parse", "enrich", "chunk", "contextualize", "metagen", "embed_index"]


@pytest.fixture
def registry() -> ProviderRegistry:
    """A real ProviderRegistry over RUNTIME_CONFIG with mocked S3 + provider cache."""
    return ProviderRegistry(
        s3=MagicMock(), provider_cache=MagicMock(), runtime_config=RUNTIME_CONFIG
    )


class TestBuildPipelineParity:
    """build_pipeline reproduces the legacy stage set, order, and inner objects."""

    def test_stage_set_and_order_match_canonical(self, registry: ProviderRegistry) -> None:
        dp = build_default_pipeline(RUNTIME_CONFIG)
        deps = StageDeps(s3=MagicMock(), postgres=MagicMock(), chunk_repo=MagicMock())
        stages = build_pipeline(dp, registry, deps, qdrant=MagicMock())
        assert [s.key for s in stages] == _CANONICAL_ORDER

    def test_inner_stage_types_match_legacy(self, registry: ProviderRegistry) -> None:
        dp = build_default_pipeline(RUNTIME_CONFIG)
        deps = StageDeps(s3=MagicMock(), postgres=MagicMock(), chunk_repo=MagicMock())
        by_key = {s.key: s for s in build_pipeline(dp, registry, deps, qdrant=MagicMock())}

        # The ingest stage is native (no legacy inner); it carries its converter resource and
        # surfaces the converter identity as its node fingerprint params.
        assert isinstance(by_key["ingest"], IngestDocStage)
        assert by_key["ingest"].fingerprint_params() == {
            "converter_name": "gotenberg",
            "converter_version": "8",
        }
        # Each remaining stage wraps the same legacy stage type the old path constructs.
        assert isinstance(by_key["parse"]._inner, S1ParseStage)
        assert isinstance(by_key["enrich"]._inner, S2EnrichStage)
        assert isinstance(by_key["chunk"]._inner, S4ChunkStage)
        assert isinstance(by_key["contextualize"]._inner, S5ContextualizeStage)
        assert isinstance(by_key["metagen"]._inner, S5bMetagenStage)
        assert isinstance(by_key["embed_index"]._inner, S6EmbedIndexStage)

    def test_inner_chains_have_identical_signatures(self, registry: ProviderRegistry) -> None:
        dp = build_default_pipeline(RUNTIME_CONFIG)
        deps = StageDeps(s3=MagicMock(), postgres=MagicMock(), chunk_repo=MagicMock())
        by_key = {s.key: s for s in build_pipeline(dp, registry, deps, qdrant=MagicMock())}

        # The assembler wires each inner stage via the SAME shared builders; the inner objects
        # must be identical to invoking those builders directly (the build_pipeline guarantee).
        assert (
            by_key["parse"]._inner.parse_chain.signature()
            == registry._build_parser_chain(dp.parse.chain, dp.parse.gate).signature()
        )
        assert (
            by_key["enrich"]._inner.params_for_fingerprint()
            == registry._build_s2(dp.enrich).params_for_fingerprint()
        )
        assert (
            by_key["chunk"]._inner.params_for_fingerprint()
            == ChunkStageAssembler.build_chunk_stage(RUNTIME_CONFIG, dp.chunk).params_for_fingerprint()
        )
        assert (
            by_key["embed_index"]._inner.embed_chain.signature()
            == registry._build_embed_chain(
                dp.embed.chain, dp.embed.gate, getattr(dp.embed, "sparse", None)
            ).signature()
        )

    def test_embed_index_omitted_without_qdrant(self, registry: ProviderRegistry) -> None:
        # No Qdrant → no indexing stage (mirrors legacy S6=None persist-only path).
        dp = build_default_pipeline(RUNTIME_CONFIG)
        deps = StageDeps(s3=MagicMock(), postgres=MagicMock(), chunk_repo=MagicMock())
        stages = build_pipeline(dp, registry, deps, qdrant=None)
        keys = [s.key for s in stages]
        assert "embed_index" not in keys
        assert keys == _CANONICAL_ORDER[:-1]
