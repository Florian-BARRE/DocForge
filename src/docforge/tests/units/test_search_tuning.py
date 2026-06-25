# ====== Code Summary ======
# Unit tests for the search tuning surface added on top of the hybrid retrieval stack:
#   - RetrieveConfig / SearchConfig parsing + backward-compatible defaults
#   - RetrievalTuning defaults, candidate_limit, from_config
#   - FieldIndexHelpers.dbsf_fuse (distribution-based score fusion)
#   - HybridSearchHelpers.resolve_vector_plan (vector_mode, field/content weights, overrides)

from common_libs.config.pipeline.stages.search_config import (
    GroupingConfig,
    RerankConfig,
    RetrieveConfig,
    SearchConfig,
)
from common_libs.search.field_index import FieldIndexHelpers, RetrievalTuning
from backend.libs.search.hybrid.helpers import HybridSearchHelpers


# ── RetrievalTuning ─────────────────────────────────────────────────────────────


class TestRetrievalTuning:
    """RetrievalTuning defaults must reproduce the historical hard-coded behavior."""

    def test_defaults_match_legacy_constants(self) -> None:
        t = RetrievalTuning()
        assert t.vector_mode == "hybrid"
        assert t.fusion == "rrf"
        assert t.rrf_k == 60
        assert t.candidate_multiplier == 3
        assert t.min_candidates == 20
        assert t.score_threshold is None
        assert t.field_weights == {}
        assert t.content_dense_weight == 1.0
        assert t.content_sparse_weight == 1.0

    def test_candidate_limit_uses_multiplier_then_floor(self) -> None:
        t = RetrievalTuning()
        # top_k * 3 wins above the floor
        assert t.candidate_limit(10) == 30
        # floor wins for small top_k
        assert t.candidate_limit(1) == 20
        assert t.candidate_limit(5) == 20

    def test_from_config_none_yields_defaults(self) -> None:
        assert RetrievalTuning.from_config(None) == RetrievalTuning()

    def test_from_config_reads_all_fields(self) -> None:
        cfg = RetrieveConfig(
            vector_mode="dense",
            fusion="dbsf",
            rrf_k=10,
            candidate_multiplier=5,
            min_candidates=50,
            score_threshold=0.25,
            field_weights={"title": 2.0},
            content_dense_weight=0.5,
            content_sparse_weight=1.5,
        )
        t = RetrievalTuning.from_config(cfg)
        assert t.vector_mode == "dense"
        assert t.fusion == "dbsf"
        assert t.rrf_k == 10
        assert t.candidate_multiplier == 5
        assert t.min_candidates == 50
        assert t.score_threshold == 0.25
        assert t.field_weights == {"title": 2.0}
        assert t.content_dense_weight == 0.5
        assert t.content_sparse_weight == 1.5


# ── SearchConfig parsing ────────────────────────────────────────────────────────


class TestSearchConfigRetrieve:
    """SearchConfig.retrieve parses cleanly and stays backward compatible."""

    def test_empty_dict_gives_default_retrieve(self) -> None:
        cfg = SearchConfig.from_dict({})
        assert cfg.retrieve.vector_mode == "hybrid"
        assert cfg.retrieve.fusion == "rrf"
        assert cfg.retrieve.grouping.enabled is False
        assert cfg.retrieve.mmr.enabled is False

    def test_partial_retrieve_round_trip(self) -> None:
        cfg = SearchConfig.from_dict(
            {"retrieve": {"fusion": "dbsf", "score_threshold": 0.3, "field_weights": {"author": 3.0}}}
        )
        assert cfg.retrieve.fusion == "dbsf"
        assert cfg.retrieve.score_threshold == 0.3
        assert cfg.retrieve.field_weights == {"author": 3.0}
        # untouched fields keep defaults
        assert cfg.retrieve.rrf_k == 60
        assert cfg.retrieve.vector_mode == "hybrid"


# ── RerankConfig provider choices ─────────────────────────────────────────────────


class TestRerankConfig:
    """
    Rerank provider choices: bge_server + cohere_rerank only; legacy bge_reranker normalizes.

    The off-the-shelf TEI reranker (`bge_reranker`) was replaced by the local bge_server host,
    which serves BGE-reranker-v2-m3 on the same /rerank contract. The `bge_reranker` choice was
    removed from the rerank discriminated union; stored configs referencing it must still load.
    """

    def test_bge_server_rerank_passes_through(self) -> None:
        """The current default rerank provider id parses cleanly when reranking is enabled."""
        cfg = SearchConfig.from_dict(
            {"rerank": {"enabled": True, "chain": [{"id": "bge_server", "base_url": "http://bge_server:80"}]}}
        )
        assert cfg.rerank.chain[0].id == "bge_server"
        assert cfg.rerank.chain[0].base_url == "http://bge_server:80"

    def test_legacy_bge_reranker_id_normalizes_to_bge_server(self) -> None:
        """
        A stored rerank config referencing the removed `bge_reranker` choice must still load and
        be rewritten to `bge_server`. Compatible fields (base_url/batch_size/locality) carry over.
        """
        cfg = SearchConfig.from_dict({
            "rerank": {
                "enabled": True,
                "chain": [{
                    "id": "bge_reranker",
                    "base_url": "http://bge_server:80",
                    "batch_size": 16,
                    "locality": "local",
                }],
            }
        })
        provider = cfg.rerank.chain[0]
        assert provider.id == "bge_server"            # legacy id rewritten
        assert provider.base_url == "http://bge_server:80"  # compatible field carried over
        assert provider.batch_size == 16               # compatible field carried over
        assert provider.locality == "local"            # compatible field carried over

    def test_unknown_rerank_id_rejected(self) -> None:
        """An unknown rerank provider id must still raise when reranking is enabled."""
        import pytest
        with pytest.raises(Exception):
            SearchConfig.from_dict({"rerank": {"enabled": True, "chain": [{"id": "not_a_reranker"}]}})

    def test_disabled_rerank_skips_chain_validation(self) -> None:
        """When reranking is disabled the chain is not validated (provider not needed)."""
        cfg = SearchConfig.from_dict({"rerank": {"enabled": False, "chain": [{"id": "anything"}]}})
        assert cfg.rerank.enabled is False


# ── RerankConfig top_n removal (FIX 3) ─────────────────────────────────────────────


class TestRerankTopNRemoved:
    """top_n was removed (request top_k is authoritative); candidate_k is the pre-rerank pool."""

    def test_top_n_field_no_longer_exists(self) -> None:
        """The dead top_n field is gone from the model schema."""
        assert "top_n" not in RerankConfig.model_fields
        assert "candidate_k" in RerankConfig.model_fields

    def test_stored_top_n_is_ignored_not_rejected(self) -> None:
        """A stored config carrying top_n still loads (extra='ignore'); the key is dropped."""
        cfg = SearchConfig.from_dict(
            {"rerank": {"enabled": False, "candidate_k": 30, "top_n": 7}}
        )
        assert cfg.rerank.candidate_k == 30
        assert not hasattr(cfg.rerank, "top_n")

    def test_candidate_k_defaults_preserved(self) -> None:
        """candidate_k keeps its historical default."""
        assert SearchConfig.from_dict({}).rerank.candidate_k == 50


# ── GroupingConfig group_by removal (FIX 1) ────────────────────────────────────────


class TestGroupingGroupByRemoved:
    """group_by was dead config (grouping is always by document_id); it was removed."""

    def test_group_by_field_no_longer_exists(self) -> None:
        """The dead group_by field is gone; enabled + group_size remain."""
        fields = GroupingConfig.model_fields
        assert "group_by" not in fields
        assert "enabled" in fields and "group_size" in fields

    def test_stored_group_by_is_ignored_not_rejected(self) -> None:
        """A stored config carrying group_by still loads (extra='ignore'); the key is dropped."""
        cfg = SearchConfig.from_dict(
            {"retrieve": {"grouping": {"enabled": True, "group_by": "author", "group_size": 4}}}
        )
        assert cfg.retrieve.grouping.enabled is True
        assert cfg.retrieve.grouping.group_size == 4
        assert not hasattr(cfg.retrieve.grouping, "group_by")


# ── DBSF fusion ─────────────────────────────────────────────────────────────────


class TestDbsfFuse:
    """Distribution-based score fusion normalizes per-vector scores then sums."""

    def test_single_vector_ranks_by_score(self) -> None:
        scored = {"content_dense": [("a", 0.9), ("b", 0.5), ("c", 0.1)]}
        fused = FieldIndexHelpers.dbsf_fuse(scored, {}, top_k=10)
        ids = [cid for cid, _ in fused]
        assert ids == ["a", "b", "c"]

    def test_cross_vector_agreement_wins(self) -> None:
        # 'b' appears strongly in both vectors → should top the fused ranking
        scored = {
            "content_dense": [("a", 0.9), ("b", 0.8)],
            "content_bm25": [("b", 9.0), ("c", 1.0)],
        }
        fused = FieldIndexHelpers.dbsf_fuse(scored, {}, top_k=10)
        assert fused[0][0] == "b"

    def test_zero_weight_vector_ignored(self) -> None:
        scored = {
            "content_dense": [("a", 0.9)],
            "content_bm25": [("z", 5.0)],
        }
        fused = FieldIndexHelpers.dbsf_fuse(scored, {"content_bm25": 0.0}, top_k=10)
        ids = [cid for cid, _ in fused]
        assert "z" not in ids
        assert "a" in ids

    def test_top_k_truncates(self) -> None:
        scored = {"content_dense": [("a", 0.9), ("b", 0.5), ("c", 0.1)]}
        fused = FieldIndexHelpers.dbsf_fuse(scored, {}, top_k=2)
        assert len(fused) == 2


# ── resolve_vector_plan ─────────────────────────────────────────────────────────


def _fields() -> list[dict]:
    """Two metadata fields: one semantic (title), one lexical (author)."""
    return [
        {"field_name": "title", "semantic": True, "lexical": False},
        {"field_name": "author", "semantic": False, "lexical": True},
    ]


class TestResolveVectorPlan:
    """resolve_vector_plan honors vector_mode, content/field weights, and overrides."""

    def test_hybrid_includes_content_and_field_vectors(self) -> None:
        dense, sparse, weights = HybridSearchHelpers.resolve_vector_plan(
            _fields(), RetrievalTuning(), None
        )
        assert "content_dense" in dense and "meta_title_dense" in dense
        assert "content_bm25" in sparse and "meta_author_bm25" in sparse
        assert weights["content_dense"] == 1.0
        assert weights["content_bm25"] == 1.0

    def test_dense_mode_drops_sparse(self) -> None:
        dense, sparse, weights = HybridSearchHelpers.resolve_vector_plan(
            _fields(), RetrievalTuning(vector_mode="dense"), None
        )
        assert sparse == []
        assert "content_bm25" not in weights
        assert "content_dense" in dense

    def test_sparse_mode_drops_dense(self) -> None:
        dense, sparse, weights = HybridSearchHelpers.resolve_vector_plan(
            _fields(), RetrievalTuning(vector_mode="sparse"), None
        )
        assert dense == []
        assert "content_dense" not in weights
        assert "content_bm25" in sparse

    def test_field_weights_applied_by_field_name(self) -> None:
        tuning = RetrievalTuning(field_weights={"title": 4.0, "author": 0.25})
        _, _, weights = HybridSearchHelpers.resolve_vector_plan(_fields(), tuning, None)
        assert weights["meta_title_dense"] == 4.0
        assert weights["meta_author_bm25"] == 0.25

    def test_content_weights_from_tuning(self) -> None:
        tuning = RetrievalTuning(content_dense_weight=2.0, content_sparse_weight=0.5)
        _, _, weights = HybridSearchHelpers.resolve_vector_plan(_fields(), tuning, None)
        assert weights["content_dense"] == 2.0
        assert weights["content_bm25"] == 0.5

    def test_request_overrides_win_over_tuning(self) -> None:
        tuning = RetrievalTuning(content_dense_weight=2.0, field_weights={"title": 4.0})
        _, _, weights = HybridSearchHelpers.resolve_vector_plan(
            _fields(), tuning, {"content_dense": 9.0, "meta_title_dense": 9.0}
        )
        assert weights["content_dense"] == 9.0
        assert weights["meta_title_dense"] == 9.0
