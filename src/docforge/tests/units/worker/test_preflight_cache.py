"""The runner's per-(collection, blob) preflight cache — the burst-ingestion probe-savings fix.

The runner preflights every provider leaf before EVERY run, so K documents on one warm collection
paid K×P live probes re-proving the same reachable endpoints. These pin the behaviour the cache
exists for and its fail-fast guarantees: within the TTL the 2nd document of a collection SKIPS the
probe; a FAILURE is never cached (the next document re-probes, so a recovered endpoint is not stuck
failing); a pipeline-blob change re-probes; and a 0 TTL disables the cache (every document probes).

The sweep is stubbed with a counter (no network). The process-wide cache is reset before each test.
"""

import uuid
from types import SimpleNamespace

import pytest
from runner import PipelineRunError, PipelineRunner
from runner.preflight_cache import PreflightCache

import shared_libs.pipelines.ingest.nodes  # noqa: F401 — registers deliver/bundle
from shared_libs.pipelines.base import ActionNode, NodeConfig, NodeInput, NodeOutput
from shared_libs.pipelines.reachability import ProbeStatus
from shared_libs.pipelines.registry import NodeRegistry
from shared_libs.public_models import (
    Chunk,
    ChunkEmbeddings,
    CollectionContract,
    DocumentIR,
    GeneratedDocumentMeta,
    IntakeResult,
    PageRenders,
    SourceDocument,
)


@NodeRegistry.register("deliver")
class _PreflightCacheProduceAll(ActionNode):
    """Produces every persistable RunBundle slot so the bundle node can close the run."""

    KIND = "test_preflight_cache_produce_all"
    NAME = "F"
    SUMMARY = "t"
    Config = NodeConfig

    class Consumes(NodeInput):
        source: SourceDocument

    class Produces(NodeOutput):
        ingest: IntakeResult
        ir: DocumentIR
        pages: PageRenders
        chunks: list[Chunk]
        document_meta: GeneratedDocumentMeta
        embeddings: ChunkEmbeddings

    async def run(
        self, data: "_PreflightCacheProduceAll.Consumes"
    ) -> "_PreflightCacheProduceAll.Produces":
        return self.Produces(
            ingest=IntakeResult(source_hash="h", pdf_content=None, page_count=1),
            ir=DocumentIR(doc_id="d", source_hash="h", n_pages=1, blocks=[]),
            pages=PageRenders(pages=[]),
            chunks=[Chunk(chunk_id="d#c0", ordinal=0, text=data.source.filename)],
            document_meta=GeneratedDocumentMeta(values={"summary": "ok"}),
            embeddings=ChunkEmbeddings(model="m", dimension=2, items=[]),
        )


def _blob(group_id: str = "pf_ingest") -> dict:
    return {
        "node_type": "group",
        "id": group_id,
        "nodes": [
            {
                "node_type": "action",
                "id": "produce",
                "family": "deliver",
                "kind": "test_preflight_cache_produce_all",
                "config": {},
            },
            {
                "node_type": "action",
                "id": "bundle",
                "family": "deliver",
                "kind": "bundle",
                "config": {},
            },
        ],
        "transitions": [{"from_node_id": "produce", "to_node_id": "bundle"}],
        "bindings": {
            "produce": {"source": {"source": "run", "field_name": "source"}},
            "bundle": {
                slot: {"source": "node", "node_id": "produce", "field_name": slot}
                for slot in ("ingest", "ir", "pages", "chunks", "document_meta", "embeddings")
            },
        },
    }


@pytest.fixture(autouse=True)
def _reset_preflight_cache() -> None:
    """The preflight cache is process-global — clear it before each test (isolation)."""
    PreflightCache.reset()


@pytest.fixture
def contract() -> CollectionContract:
    return CollectionContract(
        collection_id=uuid.uuid4(), name="c", supported_formats=["pdf"], max_file_size_bytes=10
    )


@pytest.fixture
def runner() -> PipelineRunner:
    return PipelineRunner()


def _source(name: str = "r.pdf") -> SourceDocument:
    return SourceDocument(filename=name, content=b"x", declared_meta={})


def _ok_sweep(calls: list[int]):
    """An async sweep stub that counts invocations and returns a clean (all-pass) result set."""

    async def _sweep(group, side, egress_policy):  # noqa: ANN001 — test stub
        calls.append(1)
        return []  # no non-passing leaves → preflight passes

    return _sweep


async def test_second_document_within_ttl_skips_the_probe(runner, contract, monkeypatch) -> None:
    """The cold doc probes once; the next doc on the same warm collection+blob SKIPS the probe."""
    calls: list[int] = []
    monkeypatch.setattr(runner._sweep, "sweep", _ok_sweep(calls))
    blob = _blob()
    await runner.run(
        blob, _source("a.pdf"), contract, timeout_seconds=30, preflight_cache_ttl_seconds=300
    )
    await runner.run(
        blob, _source("b.pdf"), contract, timeout_seconds=30, preflight_cache_ttl_seconds=300
    )
    assert len(calls) == 1  # the 2nd run was served from the cache


async def test_zero_ttl_disables_the_cache(runner, contract, monkeypatch) -> None:
    """A 0 TTL re-probes every document (the cache is off) — the before-this-fix behaviour."""
    calls: list[int] = []
    monkeypatch.setattr(runner._sweep, "sweep", _ok_sweep(calls))
    blob = _blob()
    await runner.run(
        blob, _source("a.pdf"), contract, timeout_seconds=30, preflight_cache_ttl_seconds=0
    )
    await runner.run(
        blob, _source("b.pdf"), contract, timeout_seconds=30, preflight_cache_ttl_seconds=0
    )
    assert len(calls) == 2


async def test_a_failure_is_not_cached_and_re_probes(runner, contract, monkeypatch) -> None:
    """A failed preflight is NEVER cached: the next document re-probes (a recovered endpoint heals)."""
    calls: list[int] = []

    async def _flaky_sweep(group, side, egress_policy):  # noqa: ANN001 — test stub
        calls.append(1)
        if len(calls) == 1:  # first doc: an endpoint is down → fail fast, do NOT cache
            return [
                SimpleNamespace(
                    node_id="llm",
                    kind="openai_compatible",
                    status=ProbeStatus.UNREACHABLE,
                    detail="down",
                )
            ]
        return []  # second doc: the endpoint recovered → clean sweep

    monkeypatch.setattr(runner._sweep, "sweep", _flaky_sweep)
    blob = _blob()
    with pytest.raises(PipelineRunError, match="preflight failed"):
        await runner.run(
            blob, _source("a.pdf"), contract, timeout_seconds=30, preflight_cache_ttl_seconds=300
        )
    # The failure was not cached: the next document probes again (and here succeeds).
    await runner.run(
        blob, _source("b.pdf"), contract, timeout_seconds=30, preflight_cache_ttl_seconds=300
    )
    assert len(calls) == 2


async def test_a_blob_change_re_probes(runner, contract, monkeypatch) -> None:
    """A different pipeline blob re-probes even within the TTL (the blob hash keys the cache)."""
    calls: list[int] = []
    monkeypatch.setattr(runner._sweep, "sweep", _ok_sweep(calls))
    await runner.run(
        _blob("v1"), _source("a.pdf"), contract, timeout_seconds=30, preflight_cache_ttl_seconds=300
    )
    await runner.run(
        _blob("v2"), _source("b.pdf"), contract, timeout_seconds=30, preflight_cache_ttl_seconds=300
    )
    assert len(calls) == 2  # the changed blob is a distinct cache key
