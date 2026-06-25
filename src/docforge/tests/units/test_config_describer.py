# ====== Code Summary ======
# Unit tests for the recursive, schema-driven config describer (config_describer.describe).
# Asserts the emitted ConfigNode tree covers the WHOLE PipelineConfig: stage gates (with
# failure_policy/on_degraded enums), the search block (retrieve + nested grouping/mmr,
# query_transform with an llm provider_union, rerank with a chain over bge_server/cohere),
# chunk.split_method exposing a NESTED embed provider_union under the semantic choice,
# chunk.atomic's four bools, and embed.sparse as an optional provider_union.

# ====== Standard Library Imports ======
from __future__ import annotations

from typing import Any

# ====== Internal Project Imports ======
from common_libs.config.pipeline import PipelineConfig
from common_libs.pipeline.assembly.config_describer import describe


# A minimal stand-in for RUNTIME_CONFIG — provider availability hooks accept any object and the
# per-collection providers ignore cfg entirely, so an empty namespace is sufficient.
class _DummyCfg:
    """Bare runtime-config stub; provider availability probes read nothing meaningful from it."""


def _tree() -> dict[str, Any]:
    """Describe the full PipelineConfig once for the assertions below."""
    return describe(PipelineConfig, _DummyCfg(), root_path="pipeline")


def _find(node: dict[str, Any], path: str) -> dict[str, Any] | None:
    """Depth-first search for the first node (anywhere in the tree) with an exact dot-path."""
    # 1. Match on this node.
    if node.get("path") == path:
        return node
    # 2. Recurse object children.
    for child in node.get("children", []):
        hit = _find(child, path)
        if hit is not None:
            return hit
    # 3. Recurse provider-choice params (the nested-union path).
    for choice in node.get("choices", []):
        for param in choice.get("params", []):
            hit = _find(param, path)
            if hit is not None:
                return hit
    return None


class TestConfigDescriber:
    def test_root_is_object_rooted_at_pipeline(self) -> None:
        tree = _tree()
        assert tree["kind"] == "object"
        assert tree["path"] == "pipeline"
        # Every top-level stage is present as a child.
        child_paths = {c["path"] for c in tree["children"]}
        assert {"pipeline.parse", "pipeline.enrich", "pipeline.chunk", "pipeline.embed", "pipeline.search"} <= child_paths

    def test_stage_gates_with_policy_enums(self) -> None:
        tree = _tree()
        # 1. Parse gate min_score is a bounded scalar.
        min_score = _find(tree, "pipeline.parse.gate.min_score")
        assert min_score is not None and min_score["kind"] == "scalar" and min_score["type"] == "float"
        assert min_score["min"] == 0.0 and min_score["max"] == 1.0
        # 2. max_duration_ms is an Optional int scalar (bound carried from the int branch).
        dur = _find(tree, "pipeline.parse.gate.max_duration_ms")
        assert dur is not None and dur["kind"] == "scalar" and dur["type"] == "int"
        # 3. failure_policy + on_degraded are enums with their exact options.
        fp = _find(tree, "pipeline.parse.gate.failure_policy")
        assert fp is not None and fp["kind"] == "enum" and set(fp["options"]) == {"raise", "continue"}
        od = _find(tree, "pipeline.parse.gate.on_degraded")
        assert od is not None and od["kind"] == "enum" and set(od["options"]) == {"empty", "best_effort"}

    def test_search_retrieve_with_nested_grouping_and_mmr(self) -> None:
        tree = _tree()
        # 1. Core retrieve scalars/enums.
        vm = _find(tree, "pipeline.search.retrieve.vector_mode")
        assert vm is not None and vm["kind"] == "enum" and set(vm["options"]) == {"hybrid", "dense", "sparse"}
        fusion = _find(tree, "pipeline.search.retrieve.fusion")
        assert fusion is not None and set(fusion["options"]) == {"rrf", "dbsf"}
        assert _find(tree, "pipeline.search.retrieve.rrf_k")["kind"] == "scalar"
        # 2. Nested grouping object.
        assert _find(tree, "pipeline.search.retrieve.grouping.enabled")["type"] == "bool"
        assert _find(tree, "pipeline.search.retrieve.grouping.group_size")["kind"] == "scalar"
        # 3. Nested mmr object.
        assert _find(tree, "pipeline.search.retrieve.mmr.enabled")["type"] == "bool"
        assert _find(tree, "pipeline.search.retrieve.mmr.diversity")["kind"] == "scalar"
        assert _find(tree, "pipeline.search.retrieve.mmr.candidates_limit")["kind"] == "scalar"

    def test_query_transform_llm_provider_union(self) -> None:
        tree = _tree()
        # 1. strategy is an enum.
        strat = _find(tree, "pipeline.search.query_transform.strategy")
        assert strat is not None and set(strat["options"]) == {"none", "rewrite", "hyde", "multi_query"}
        assert _find(tree, "pipeline.search.query_transform.n_variants")["kind"] == "scalar"
        # 2. llm is an OPTIONAL single provider_union over the llm category.
        llm = _find(tree, "pipeline.search.query_transform.llm")
        assert llm is not None and llm["kind"] == "provider_union"
        assert llm["multi"] is False and llm["optional"] is True
        assert llm["capability"] == "llm"
        assert "openai_compat" in {c["id"] for c in llm["choices"]}

    def test_rerank_chain_over_providers(self) -> None:
        tree = _tree()
        assert _find(tree, "pipeline.search.rerank.enabled")["type"] == "bool"
        assert _find(tree, "pipeline.search.rerank.candidate_k")["kind"] == "scalar"
        chain = _find(tree, "pipeline.search.rerank.chain")
        assert chain is not None and chain["kind"] == "chain" and chain["multi"] is True
        assert chain["capability"] == "rerank"
        ids = {c["id"] for c in chain["choices"]}
        assert {"bge_server", "cohere_rerank"} <= ids

    def test_chunk_atomic_four_bools(self) -> None:
        tree = _tree()
        for field in ("tables", "figures", "formulas", "keep_caption_with_figure"):
            node = _find(tree, f"pipeline.chunk.atomic.{field}")
            assert node is not None and node["kind"] == "scalar" and node["type"] == "bool"

    def test_split_method_exposes_nested_embed_union(self) -> None:
        tree = _tree()
        # 1. split_method is a single provider_union over the split_method category.
        sm = _find(tree, "pipeline.chunk.split_method")
        assert sm is not None and sm["kind"] == "provider_union" and sm["capability"] == "split_method"
        ids = {c["id"] for c in sm["choices"]}
        assert {"token_budget", "semantic", "sentence_window"} <= ids
        # 2. The semantic choice exposes a NESTED embed provider_union among its params.
        semantic = next(c for c in sm["choices"] if c["id"] == "semantic")
        embed_param = next((p for p in semantic["params"] if p.get("capability") == "embed"), None)
        assert embed_param is not None and embed_param["kind"] == "provider_union"
        assert "bge_server" in {c["id"] for c in embed_param["choices"]}

    def test_embed_chain_and_optional_sparse(self) -> None:
        tree = _tree()
        chain = _find(tree, "pipeline.embed.chain")
        assert chain is not None and chain["kind"] == "chain" and chain["capability"] == "embed"
        sparse = _find(tree, "pipeline.embed.sparse")
        assert sparse is not None and sparse["kind"] == "provider_union"
        assert sparse["multi"] is False and sparse["optional"] is True
        assert sparse["capability"] == "embed"

    def test_provider_choice_secret_field_masked(self) -> None:
        tree = _tree()
        # The embed chain's bge_server choice exposes api_key as a `secret` scalar.
        chain = _find(tree, "pipeline.embed.chain")
        bge = next(c for c in chain["choices"] if c["id"] == "bge_server")
        api_key = next((p for p in bge["params"] if p["path"] == "api_key"), None)
        assert api_key is not None and api_key["type"] == "secret"
