# ====== Code Summary ======
# Unit tests for S5bMetagenStage.run — the LLM-generated metadata stage.
# All LLM calls and cache I/O are mocked; no network, no Postgres, no S3.
# Covers: no-op short-circuit (empty chain / empty targets), chunk-scope writes
# derived_meta, doc-scope populates doc_fields, one combined call per chunk,
# budget short-circuit, ProviderCallCache hit (chain not called), graceful degrade
# on provider error (empty result, no exception).

from __future__ import annotations

import json
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from common_libs.config.pipeline.stages.metagen_config import MetaGenTarget
from common_libs.domain.ir.chunk import Chunk
from common_libs.domain.ir.models import DocumentIR
from common_libs.domain.metadata.meta_field_spec import MetaFieldSpec
from common_libs.pipeline.stages.s5b_metagen.core import S5bMetagenStage
from common_libs.pipeline.bricks.chain.models import ChainOutcome


# ─── Factories ─────────────────────────────────────────────────────────────────

def _chunk(raw_text: str = "Some chunk content about Python.") -> Chunk:
    """Build a minimal Chunk."""
    return Chunk(
        id=str(uuid.uuid4()),
        document_id=str(uuid.uuid4()),
        config_hash="cfg",
        block_ids=["b1"],
        raw_text=raw_text,
        embed_text="",
        token_count=10,
        strategy="recursive_structure_aware",
    )


def _ir(title: str = "Test Document") -> DocumentIR:
    """Build a minimal DocumentIR with no text blocks."""
    return DocumentIR(
        doc_id=str(uuid.uuid4()),
        title=title,
        source_hash="sha256test",
        n_pages=1,
        language="en",
        blocks=[],
    )


def _spec(name: str, ftype: str = "string", required: bool = True) -> MetaFieldSpec:
    """Build a MetaFieldSpec for a generated field."""
    return MetaFieldSpec(field_name=name, field_type=ftype, required=required, origin="generated")


def _target(field: str, scope: str = "chunk", prompt: str = "Extract.") -> MetaGenTarget:
    """Build a MetaGenTarget."""
    return MetaGenTarget(field=field, scope=scope, prompt=prompt)


def _make_chain(result: dict | None = None, degraded: bool = False) -> MagicMock:
    """
    Build a mock Chain that returns a ChainOutcome when .call() is awaited.

    The mock's `call` method is an AsyncMock that accepts a callable (the lambda
    the stage passes) and returns the configured ChainOutcome.
    """
    outcome = ChainOutcome(
        result=result if result is not None else {},
        attempts=[],
        final_provider="openai_compat" if not degraded else None,
        degraded=degraded,
    )
    chain = MagicMock()
    chain.providers = [MagicMock()]
    chain.first_provider_name = "openai_compat"
    chain.call = AsyncMock(return_value=outcome)
    return chain


def _make_cache(cached_json: str | None = None) -> MagicMock:
    """
    Build a mock ProviderCallCache.

    Args:
        cached_json: If set, `get` returns this JSON string (cache hit).
                     If None, `get` returns None (cache miss).
    """
    cache = MagicMock()
    cache.get = AsyncMock(return_value=cached_json)
    cache.put = AsyncMock()
    return cache


def _make_stage(
    chain=None,
    targets: list | None = None,
    field_types: dict | None = None,
    cache=None,
    max_concurrency: int = 8,
    max_budget_usd: float = 0.0,
) -> S5bMetagenStage:
    """Build an S5bMetagenStage with sensible defaults for testing."""
    return S5bMetagenStage(
        llm_chain=chain,
        targets=targets or [],
        field_types=field_types or {},
        provider_cache=cache or _make_cache(),
        max_concurrency=max_concurrency,
        max_budget_usd=max_budget_usd,
    )


# ─── No-op short-circuit ───────────────────────────────────────────────────────

class TestNoOpShortCircuit:
    """Stage must exit cleanly when there is nothing to generate."""

    @pytest.mark.asyncio
    async def test_no_chain_returns_noop_result(self) -> None:
        """llm_chain=None → S5bResult with empty doc_fields and n_generated=0."""
        stage = _make_stage(chain=None, targets=[_target("kw")])
        result = await stage.run([_chunk()], _ir())
        assert result.n_generated == 0
        assert result.doc_fields == {}
        assert result.chain_traces == []

    @pytest.mark.asyncio
    async def test_empty_chain_providers_returns_noop(self) -> None:
        """A chain with no providers (providers=[]) is treated as disabled."""
        chain = MagicMock()
        chain.providers = []
        stage = _make_stage(chain=chain, targets=[_target("kw")])
        result = await stage.run([_chunk()], _ir())
        assert result.n_generated == 0

    @pytest.mark.asyncio
    async def test_empty_targets_returns_noop(self) -> None:
        """No targets → no-op (chain is present but there is nothing to extract)."""
        stage = _make_stage(chain=_make_chain(), targets=[])
        result = await stage.run([_chunk()], _ir())
        assert result.n_generated == 0

    @pytest.mark.asyncio
    async def test_targets_with_unknown_fields_returns_noop(self) -> None:
        """Targets whose fields are absent from field_types are skipped → no-op."""
        stage = _make_stage(
            chain=_make_chain(result={"kw": "python"}),
            targets=[_target("kw")],
            field_types={},  # kw has no entry
        )
        result = await stage.run([_chunk()], _ir())
        assert result.n_generated == 0


# ─── Chunk-scope generation ────────────────────────────────────────────────────

class TestChunkScopeGeneration:
    """Chunk-scope targets write into chunk.derived_meta."""

    @pytest.mark.asyncio
    async def test_generated_value_written_to_derived_meta(self) -> None:
        """A chunk-scope hit writes the LLM's value into chunk.derived_meta."""
        chunk = _chunk("Python is great for data science.")
        chain = _make_chain(result={"kw": "python"})
        cache = _make_cache(cached_json=None)  # miss
        stage = _make_stage(
            chain=chain,
            targets=[_target("kw", scope="chunk")],
            field_types={"kw": _spec("kw", "string")},
            cache=cache,
        )
        result = await stage.run([chunk], _ir())
        assert chunk.derived_meta["kw"] == "python"
        assert result.n_generated == 1

    @pytest.mark.asyncio
    async def test_null_value_not_written_to_derived_meta(self) -> None:
        """A null LLM return for a key is NOT written into derived_meta."""
        chunk = _chunk()
        chain = _make_chain(result={"kw": None})
        stage = _make_stage(
            chain=chain,
            targets=[_target("kw", scope="chunk")],
            field_types={"kw": _spec("kw", "string", required=False)},
            cache=_make_cache(),
        )
        result = await stage.run([chunk], _ir())
        assert "kw" not in chunk.derived_meta
        assert result.n_generated == 0

    @pytest.mark.asyncio
    async def test_one_combined_call_per_chunk(self) -> None:
        """Two chunk-scope targets produce ONE chain.call per chunk (combined schema)."""
        chunks = [_chunk(f"chunk {i}") for i in range(3)]
        chain = _make_chain(result={"kw": "python", "lang": "en"})
        cache = _make_cache(cached_json=None)
        stage = _make_stage(
            chain=chain,
            targets=[_target("kw", "chunk"), _target("lang", "chunk")],
            field_types={"kw": _spec("kw"), "lang": _spec("lang")},
            cache=cache,
        )
        result = await stage.run(chunks, _ir())
        # One call per chunk (all targets combined), total = 3 calls for 3 chunks.
        assert chain.call.call_count == 3
        # Both fields filled per chunk → 6 generated values total.
        assert result.n_generated == 6
        for c in chunks:
            assert c.derived_meta.get("kw") == "python"
            assert c.derived_meta.get("lang") == "en"

    @pytest.mark.asyncio
    async def test_multiple_chunks_each_get_their_own_derived_meta(self) -> None:
        """Each chunk object gets its own derived_meta written independently."""
        chunks = [_chunk(f"text_{i}") for i in range(2)]

        call_idx = 0

        async def _side_effect(fn):
            nonlocal call_idx
            results = [{"kw": "alpha"}, {"kw": "beta"}]
            out = results[call_idx % len(results)]
            call_idx += 1
            return ChainOutcome(result=out, attempts=[], final_provider="openai_compat", degraded=False)

        chain = MagicMock()
        chain.providers = [MagicMock()]
        chain.first_provider_name = "openai_compat"
        chain.call = AsyncMock(side_effect=_side_effect)

        stage = _make_stage(
            chain=chain,
            targets=[_target("kw", "chunk")],
            field_types={"kw": _spec("kw")},
            cache=_make_cache(),
        )
        await stage.run(chunks, _ir())
        assert chunks[0].derived_meta.get("kw") == "alpha"
        assert chunks[1].derived_meta.get("kw") == "beta"


# ─── Doc-scope generation ──────────────────────────────────────────────────────

class TestDocScopeGeneration:
    """Document-scope targets return doc_fields; chunks are untouched."""

    @pytest.mark.asyncio
    async def test_doc_scope_populates_doc_fields(self) -> None:
        """A document-scope target writes into result.doc_fields."""
        chain = _make_chain(result={"summary": "A paper about ML."})
        stage = _make_stage(
            chain=chain,
            targets=[_target("summary", scope="document", prompt="Summarise.")],
            field_types={"summary": _spec("summary")},
            cache=_make_cache(),
        )
        chunk = _chunk()
        result = await stage.run([chunk], _ir())
        assert result.doc_fields["summary"] == "A paper about ML."
        # chunk.derived_meta must NOT be touched for a doc-scope target
        assert "summary" not in chunk.derived_meta

    @pytest.mark.asyncio
    async def test_doc_scope_one_call_per_document(self) -> None:
        """Document-scope triggers exactly one chain.call regardless of chunk count."""
        chain = _make_chain(result={"summary": "x"})
        stage = _make_stage(
            chain=chain,
            targets=[_target("summary", scope="document")],
            field_types={"summary": _spec("summary")},
            cache=_make_cache(),
        )
        chunks = [_chunk() for _ in range(5)]
        await stage.run(chunks, _ir())
        # One doc-scope call only (chain is only touched once for the whole document)
        assert chain.call.call_count == 1


# ─── Budget short-circuit ──────────────────────────────────────────────────────

class TestBudgetShortCircuit:
    """When estimated cost exceeds the cap, the stage skips generation entirely."""

    @pytest.mark.asyncio
    async def test_budget_exceeded_returns_noop_result(self) -> None:
        """A tiny budget cap causes the stage to skip generation and return empty results."""
        chunks = [_chunk("very long text " * 200) for _ in range(10)]
        chain = _make_chain(result={"kw": "python"})
        stage = _make_stage(
            chain=chain,
            targets=[_target("kw", "chunk")],
            field_types={"kw": _spec("kw")},
            cache=_make_cache(),
            max_budget_usd=0.000001,  # Effectively zero — any doc will exceed this
        )
        result = await stage.run(chunks, _ir())
        assert result.n_generated == 0
        assert result.doc_fields == {}
        # The chain must never be called when the budget gate fires
        chain.call.assert_not_called()

    @pytest.mark.asyncio
    async def test_zero_budget_means_unlimited(self) -> None:
        """max_budget_usd=0 disables the budget gate (0 = unlimited)."""
        chain = _make_chain(result={"kw": "python"})
        stage = _make_stage(
            chain=chain,
            targets=[_target("kw", "chunk")],
            field_types={"kw": _spec("kw")},
            cache=_make_cache(),
            max_budget_usd=0.0,
        )
        result = await stage.run([_chunk()], _ir())
        # Generation proceeds normally when the cap is 0.
        assert result.n_generated == 1


# ─── Provider-call cache ───────────────────────────────────────────────────────

class TestProviderCallCache:
    """Cache hits must be served without invoking the chain; misses trigger a real call."""

    @pytest.mark.asyncio
    async def test_cache_hit_does_not_call_chain(self) -> None:
        """A cache hit serves the cached JSON; the chain is never invoked."""
        cached = json.dumps({"kw": "cached-python"})
        cache = _make_cache(cached_json=cached)
        chain = _make_chain(result={"kw": "fresh-python"})
        stage = _make_stage(
            chain=chain,
            targets=[_target("kw", "chunk")],
            field_types={"kw": _spec("kw")},
            cache=cache,
        )
        chunk = _chunk()
        result = await stage.run([chunk], _ir())
        chain.call.assert_not_called()
        assert chunk.derived_meta["kw"] == "cached-python"
        assert result.n_generated == 1

    @pytest.mark.asyncio
    async def test_cache_miss_calls_chain_and_stores_result(self) -> None:
        """A cache miss triggers a chain call and the result is persisted via cache.put."""
        cache = _make_cache(cached_json=None)  # always miss
        chain = _make_chain(result={"kw": "fresh"})
        stage = _make_stage(
            chain=chain,
            targets=[_target("kw", "chunk")],
            field_types={"kw": _spec("kw")},
            cache=cache,
        )
        await stage.run([_chunk()], _ir())
        chain.call.assert_called_once()
        cache.put.assert_called_once()

    @pytest.mark.asyncio
    async def test_corrupt_cache_entry_falls_through_to_chain(self) -> None:
        """An unparseable cache entry (not valid JSON) is ignored; the chain is called."""
        cache = _make_cache(cached_json="NOT VALID JSON{{{{")
        chain = _make_chain(result={"kw": "fresh"})
        stage = _make_stage(
            chain=chain,
            targets=[_target("kw", "chunk")],
            field_types={"kw": _spec("kw")},
            cache=cache,
        )
        chunk = _chunk()
        await stage.run([chunk], _ir())
        chain.call.assert_called_once()
        assert chunk.derived_meta.get("kw") == "fresh"


# ─── Graceful degrade ─────────────────────────────────────────────────────────

class TestGracefulDegrade:
    """Provider errors / empty results must never fail the document."""

    @pytest.mark.asyncio
    async def test_empty_llm_result_writes_nothing(self) -> None:
        """An empty dict from the chain means the field is left empty; no exception raised."""
        chain = _make_chain(result={}, degraded=True)
        stage = _make_stage(
            chain=chain,
            targets=[_target("kw", "chunk")],
            field_types={"kw": _spec("kw")},
            cache=_make_cache(),
        )
        chunk = _chunk()
        result = await stage.run([chunk], _ir())
        assert "kw" not in chunk.derived_meta
        assert result.n_generated == 0

    @pytest.mark.asyncio
    async def test_provider_error_degrades_not_raises(self) -> None:
        """
        If the chain returns a non-dict result (degraded), the stage degrades gracefully.
        The chunk is left untouched and no exception propagates.
        """
        outcome = ChainOutcome(result=None, attempts=[], final_provider=None, degraded=True)
        chain = MagicMock()
        chain.providers = [MagicMock()]
        chain.first_provider_name = "openai_compat"
        chain.call = AsyncMock(return_value=outcome)

        stage = _make_stage(
            chain=chain,
            targets=[_target("kw", "chunk")],
            field_types={"kw": _spec("kw")},
            cache=_make_cache(),
        )
        chunk = _chunk()
        result = await stage.run([chunk], _ir())
        assert "kw" not in chunk.derived_meta
        assert result.n_generated == 0


# ─── Mixed-scope ──────────────────────────────────────────────────────────────

class TestMixedScope:
    """Chunk-scope and doc-scope targets can coexist in one run."""

    @pytest.mark.asyncio
    async def test_chunk_and_doc_scope_targets(self) -> None:
        """Both scopes produce results in the same run."""
        call_count = 0

        async def _side_effect(fn):
            nonlocal call_count
            call_count += 1
            # First 1 call is the doc-scope; remaining are chunk-scope (or vice versa — order
            # depends on gather; we just return a valid dict for both).
            return ChainOutcome(result={"kw": "py", "summary": "A doc."}, attempts=[], final_provider="p", degraded=False)

        chain = MagicMock()
        chain.providers = [MagicMock()]
        chain.first_provider_name = "openai_compat"
        chain.call = AsyncMock(side_effect=_side_effect)

        chunks = [_chunk()]
        stage = _make_stage(
            chain=chain,
            targets=[_target("kw", "chunk"), _target("summary", "document")],
            field_types={"kw": _spec("kw"), "summary": _spec("summary")},
            cache=_make_cache(),
        )
        result = await stage.run(chunks, _ir())
        # At least one write for chunk + at least one for doc
        assert result.n_generated >= 1
