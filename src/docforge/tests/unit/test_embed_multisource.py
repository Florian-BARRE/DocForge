# ====== Code Summary ======
# Unit tests for multi-source embedding: EmbedConfig.sparse (a separate sparse backend
# alongside the dense chain) and CompositeEmbedProvider (dense from one backend, sparse
# from another, merged into one EmbedResult). Enables hybrid search with a dense-only
# dense backend (e.g. OpenAI) paired with a local sparse backend (e.g. SPLADE TEI).

import asyncio

from libs.config.pipeline.stages.embed_config import EmbedConfig
from libs.providers.embed.composite import CompositeEmbedProvider
from libs.providers.results.embed_result import EmbedResult


# ── EmbedConfig.sparse parsing ──────────────────────────────────────────────────


class TestEmbedConfigSparse:
    def test_dense_chain_plus_separate_sparse(self) -> None:
        cfg = EmbedConfig.model_validate({
            "chain": [{"id": "openai", "base_url": "https://api.openai.com/v1",
                       "api_key": "sk-x", "model": "text-embedding-3-large"}],
            "sparse": {"id": "tei", "base_url": "http://tei-sparse:80", "embed_sparse": True},
        })
        # Legacy id "openai" is unified to openai_compat with locality="external".
        assert cfg.chain[0].id == "openai_compat"
        assert cfg.chain[0].locality == "external"
        assert cfg.chain[0].api_key == "sk-x"
        assert cfg.sparse is not None and cfg.sparse.id == "tei"

    def test_unified_local_openai_compat(self) -> None:
        cfg = EmbedConfig.model_validate(
            {"chain": [{"id": "openai_compat", "locality": "local", "base_url": "http://vllm:8000/v1"}]}
        )
        assert cfg.chain[0].id == "openai_compat"
        assert cfg.chain[0].locality == "local"

    def test_no_sparse_defaults_to_none(self) -> None:
        cfg = EmbedConfig.model_validate({"chain": [{"id": "tei"}]})
        assert cfg.sparse is None

    def test_unknown_sparse_id_rejected(self) -> None:
        import pytest
        with pytest.raises(Exception):
            EmbedConfig.model_validate({"chain": [{"id": "tei"}], "sparse": {"id": "nope"}})


# ── CompositeEmbedProvider ──────────────────────────────────────────────────────


class _Fake:
    def __init__(self, name, dim, vectors, sparse, model):
        self.name, self.version, self.runs_on = name, name, "local"
        self._dim, self._vectors, self._sparse, self._model = dim, vectors, sparse, model

    @property
    def dimension(self):
        return self._dim

    async def embed(self, texts):
        n = len(texts)
        return EmbedResult(
            vectors=[list(self._vectors) for _ in range(n)],
            sparse=[dict(self._sparse) for _ in range(n)] if self._sparse is not None else None,
            model=self._model,
        )


class TestCompositeEmbedProvider:
    def test_merges_dense_and_sparse_from_distinct_backends(self) -> None:
        dense = _Fake("dense", 3, [1.0, 2.0, 3.0], None, "dense-m")
        sparse = _Fake("sparse", 0, [], {7: 0.9}, "sparse-m")
        comp = CompositeEmbedProvider(dense=dense, sparse=sparse)
        res = asyncio.run(comp.embed(["a", "b"]))
        assert comp.dimension == 3                      # dense defines the dimension
        assert res.vectors == [[1.0, 2.0, 3.0], [1.0, 2.0, 3.0]]
        assert res.sparse == [{7: 0.9}, {7: 0.9}]       # sparse from the sparse backend
        assert res.model == "dense-m"                   # dense identity preserved
        assert comp.name == "dense"

    def test_empty_input(self) -> None:
        comp = CompositeEmbedProvider(
            dense=_Fake("d", 3, [1.0], None, "d"), sparse=_Fake("s", 0, [], {1: 1.0}, "s")
        )
        res = asyncio.run(comp.embed([]))
        assert res.vectors == [] and res.sparse is None
