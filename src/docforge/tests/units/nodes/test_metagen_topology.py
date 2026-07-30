"""The externalised metagen topology (prep -> ForEach(structgen chain [+ skip]) -> apply), for both
scopes — the shape the P5c stage rewire emits.

A FAKE structgen kind returns canned answers so the ONLY thing under test is the new topology (the
coercion path is proven in test_structgen.py). The absolute expected values below were locked in P5b
against the (now-deleted) monolithic metagen node — parity is frozen here as literal assertions.
on_error is verified as a GRAPH EDGE (skip terminal vs a propagating item failure), and the loud
bad-target guard is verified to still fire in prep.
"""

import uuid

import pytest

from shared_libs.pipelines.build import PipelineBuilder
from shared_libs.pipelines.engine import FlowEngine
from shared_libs.pipelines.ingest.nodes.metagen.base import MetagenOnError
from shared_libs.pipelines.ingest.nodes.metagen.prep.chunk import (
    MetagenChunkPrepConfig,
    MetagenChunkPrepConsumes,
    MetagenChunkPrepNode,
)
from shared_libs.pipelines.ingest.nodes.metagen.prep.document import (
    MetagenDocumentPrepConfig,
    MetagenDocumentPrepConsumes,
    MetagenDocumentPrepNode,
)
from shared_libs.pipelines.ingest.stages.metagen_body import MetagenBodyBuilder
from shared_libs.pipelines.ingest.stages.models import ChainStep
from shared_libs.pipelines.ingest.stages.state import ChainSpec
from shared_libs.pipelines.nodes.structgen.openai_compatible.core import (
    StructGenOpenAICompatibleNode,
)
from shared_libs.pipelines.registry import NodeRegistry
from shared_libs.pipelines.validation import GraphValidator
from shared_libs.public_models import (
    Chunk,
    CollectionContract,
    FieldOrigin,
    FieldScope,
    FieldType,
    MetadataFieldSpec,
)

# ---------------------------------------------------------------------------
# Fixtures — ported from test_metagen_stage.py so parity is judged on identical input.
# ---------------------------------------------------------------------------


def _spec(name: str, field_type: FieldType, scope: FieldScope) -> MetadataFieldSpec:
    return MetadataFieldSpec(
        field_name=name, field_type=field_type, origin=FieldOrigin.GENERATED, scope=scope
    )


CONTRACT = CollectionContract(
    collection_id=uuid.uuid4(),
    name="c",
    supported_formats=["pdf"],
    max_file_size_bytes=1,
    fields=[
        MetadataFieldSpec(field_name="title", field_type=FieldType.STRING),  # USER field: ignored
        _spec("summary", FieldType.STRING, FieldScope.DOCUMENT),
        _spec("year", FieldType.INTEGER, FieldScope.DOCUMENT),
        _spec("published_at", FieldType.DATETIME, FieldScope.DOCUMENT),
        _spec("keywords", FieldType.KEYWORD_LIST, FieldScope.CHUNK),
        _spec("relevance", FieldType.FLOAT, FieldScope.CHUNK),
    ],
)
CHUNKS = [
    Chunk(chunk_id="d#c0", ordinal=0, text="Cats purr softly.", context="Section: Animals"),
    Chunk(chunk_id="d#c1", ordinal=1, text="Bonds fell sharply."),
]

# Canned raw model answers per requested field (pre-coercion) — identical to test_metagen_stage.
ANSWERS: dict[str, object] = {
    "summary": "  A report about cats and bonds. ",
    "year": "2024",
    "published_at": "2024-03-01T10:00:00",
    "keywords": ["cats", " bonds ", ""],
    "relevance": "not-a-number",  # uncoercible -> dropped
}

FAKE_STRUCTGEN_KIND = "test_topology_structgen_fake"
FAIL_SENTINEL = "sharply"  # a text the fake structgen refuses (simulated 503)


@NodeRegistry.register("structgen")
class FakeStructGenNode(StructGenOpenAICompatibleNode):
    """Returns canned answers per field; raises for a request whose text carries the sentinel."""

    KIND = FAKE_STRUCTGEN_KIND
    NAME = "F"
    SUMMARY = "t"

    async def _generate(self, schema, request, endpoint):
        # A chunk-scope request over the sentinel text fails (a 503); the document view also carries
        # the sentinel but its requests have chunk_id=None, so only chunk-scope requests refuse.
        if request.chunk_id is not None and FAIL_SENTINEL in request.text:
            raise RuntimeError("model 503")
        return {name: ANSWERS.get(name) for name in schema["properties"]}


# ---------------------------------------------------------------------------
# Blob assembly — the new topology as a dict blob (what P5c emits).
# ---------------------------------------------------------------------------

_ENDPOINT = {"base_url": "http://x", "model": "m"}


def _chain(steps: list[dict] | None = None) -> ChainSpec:
    """A structgen chain of the FAKE kind (1 step unless a fallback is asked for)."""
    steps = steps or [{"kind": FAKE_STRUCTGEN_KIND, "config": {}}]
    return ChainSpec(family="structgen", steps=[ChainStep(**step) for step in steps])


def _chunk_blob(
    prep_config: dict, on_error: MetagenOnError, chain: ChainSpec | None = None
) -> dict:
    """prep(chunk) -> ForEach(structgen chain) -> chunk_apply."""
    body = MetagenBodyBuilder.build(chain or _chain(), on_error)
    return {
        "node_type": "group",
        "id": "metagen_chunk",
        "nodes": [
            {
                "node_type": "action",
                "id": "prep",
                "family": "metagen",
                "kind": "chunk_prep",
                "config": prep_config,
            },
            {
                "node_type": "foreach",
                "id": "loop",
                "item_field": "request",
                "max_concurrency": 4,
                "over": {"source": "node", "node_id": "prep", "field_name": "requests"},
                "body": body.model_dump(),
            },
            {
                "node_type": "action",
                "id": "apply",
                "family": "metagen",
                "kind": "chunk_apply",
                "config": {},
            },
        ],
        "transitions": [
            {"from_node_id": "prep", "to_node_id": "loop"},
            {"from_node_id": "loop", "to_node_id": "apply"},
        ],
        "bindings": {
            "prep": {
                "chunks": {"source": "run", "field_name": "chunks"},
                "contract": {"source": "run", "field_name": "contract"},
            },
            "apply": {
                "chunks": {"source": "run", "field_name": "chunks"},
                "values": {"source": "node", "node_id": "loop", "field_name": "items"},
            },
        },
    }


def _document_blob(
    prep_config: dict, on_error: MetagenOnError, chain: ChainSpec | None = None
) -> dict:
    """prep(document) -> ForEach(structgen chain) -> document_apply."""
    body = MetagenBodyBuilder.build(chain or _chain(), on_error)
    return {
        "node_type": "group",
        "id": "metagen_document",
        "nodes": [
            {
                "node_type": "action",
                "id": "prep",
                "family": "metagen",
                "kind": "document_prep",
                "config": prep_config,
            },
            {
                "node_type": "foreach",
                "id": "loop",
                "item_field": "request",
                "max_concurrency": 4,
                "over": {"source": "node", "node_id": "prep", "field_name": "requests"},
                "body": body.model_dump(),
            },
            {
                "node_type": "action",
                "id": "apply",
                "family": "metagen",
                "kind": "document_apply",
                "config": {},
            },
        ],
        "transitions": [
            {"from_node_id": "prep", "to_node_id": "loop"},
            {"from_node_id": "loop", "to_node_id": "apply"},
        ],
        "bindings": {
            "prep": {
                "chunks": {"source": "run", "field_name": "chunks"},
                "contract": {"source": "run", "field_name": "contract"},
            },
            "apply": {"values": {"source": "node", "node_id": "loop", "field_name": "items"}},
        },
    }


# ---------------------------------------------------------------------------
# 1. BUILD + validate (both scopes).
# ---------------------------------------------------------------------------


def test_chunk_topology_builds_and_validates() -> None:
    group = PipelineBuilder().build(_chunk_blob(dict(_ENDPOINT), MetagenOnError.SKIP_FIELDS))
    assert GraphValidator().validate(group) == []


def test_document_topology_builds_and_validates() -> None:
    group = PipelineBuilder().build(_document_blob(dict(_ENDPOINT), MetagenOnError.SKIP_FIELDS))
    assert GraphValidator().validate(group) == []


def test_fallback_chain_topology_builds_and_validates() -> None:
    """A 2-step structgen chain (escalate on failure) + skip terminal still validates."""
    chain = _chain(
        [
            {"kind": FAKE_STRUCTGEN_KIND, "config": {}},
            {"kind": "openai_compatible", "config": {"base_url": "http://robust", "model": "big"}},
        ]
    )
    group = PipelineBuilder().build(_chunk_blob(dict(_ENDPOINT), MetagenOnError.SKIP_FIELDS, chain))
    assert GraphValidator().validate(group) == []


# ---------------------------------------------------------------------------
# 2. Behaviour of the topology (chunk + document, both groupings) — frozen expected values.
# ---------------------------------------------------------------------------


async def _run_new(blob: dict, chunks: list[Chunk]) -> object:
    group = PipelineBuilder().build(blob)
    output, _record = await FlowEngine().execute(group, {"chunks": chunks, "contract": CONTRACT})
    return output


async def test_chunk_combined_grouping() -> None:
    prep_config = {**_ENDPOINT, "grouping": "combined"}
    # skip_fields so the "sharply" chunk drops its fields (the doc survives).
    new = await _run_new(_chunk_blob(prep_config, MetagenOnError.SKIP_FIELDS), CHUNKS)
    new_meta = [chunk.generated_meta for chunk in new.chunks]
    assert new_meta == [{"keywords": ["cats", "bonds"]}, {}]  # relevance dropped, c1 503 -> skipped


async def test_chunk_per_field_grouping() -> None:
    prep_config = {**_ENDPOINT, "grouping": "per_field"}
    new = await _run_new(_chunk_blob(prep_config, MetagenOnError.SKIP_FIELDS), CHUNKS)
    assert [c.generated_meta for c in new.chunks] == [{"keywords": ["cats", "bonds"]}, {}]


async def test_chunk_merge_not_clobber() -> None:
    """A chunk already carrying generated_meta keeps it — the topology merges, never clobbers."""
    pre = [
        CHUNKS[0].model_copy(update={"generated_meta": {"topic": "cats"}}),
        CHUNKS[1],
    ]
    new = await _run_new(_chunk_blob({**_ENDPOINT}, MetagenOnError.SKIP_FIELDS), pre)
    assert new.chunks[0].generated_meta == {"topic": "cats", "keywords": ["cats", "bonds"]}


async def test_document_combined_grouping() -> None:
    new = await _run_new(
        _document_blob({**_ENDPOINT, "grouping": "combined"}, MetagenOnError.FAIL), CHUNKS
    )
    assert new.meta.values == {
        "summary": "A report about cats and bonds.",
        "year": 2024,
        "published_at": "2024-03-01T10:00:00",
    }


async def test_document_per_field_grouping_joins_multiple_values() -> None:
    """per_field -> one request (hence one GeneratedValues) per field; document_apply joins them all."""
    new = await _run_new(
        _document_blob({**_ENDPOINT, "grouping": "per_field"}, MetagenOnError.FAIL), CHUNKS
    )
    assert new.meta.values == {
        "summary": "A report about cats and bonds.",
        "year": 2024,
        "published_at": "2024-03-01T10:00:00",
    }
    assert set(new.meta.values) == {"summary", "year", "published_at"}  # three groups joined


# ---------------------------------------------------------------------------
# 3. on_error as a graph edge — skip terminal vs a propagating item failure.
# ---------------------------------------------------------------------------


async def test_skip_fields_survives_a_failed_request() -> None:
    """skip_fields: the 'sharply' chunk's failed request routes to metagen_skip -> empty, doc alive."""
    output = await _run_new(_chunk_blob(dict(_ENDPOINT), MetagenOnError.SKIP_FIELDS), CHUNKS)
    assert output is not None  # the run completed
    assert output.chunks[0].generated_meta == {"keywords": ["cats", "bonds"]}
    assert output.chunks[1].generated_meta == {}  # the failed request's fields stay absent


async def test_fail_propagates_as_an_item_failure() -> None:
    """fail: no skip terminal, so the failed request fails the ForEach item and the whole run."""
    group = PipelineBuilder().build(_chunk_blob(dict(_ENDPOINT), MetagenOnError.FAIL))
    output, record = await FlowEngine().execute(group, {"chunks": CHUNKS, "contract": CONTRACT})
    assert output is None  # the run failed loudly (no fail-soft edge)
    assert record.status.value == "failed"


# ---------------------------------------------------------------------------
# 4. Loud bad-target still fires in prep (before any structgen call).
# ---------------------------------------------------------------------------


async def test_bad_target_raises_in_chunk_prep() -> None:
    bad = MetagenChunkPrepConfig(**_ENDPOINT, targets=[{"field": "nope"}])
    with pytest.raises(ValueError, match="nope"):
        await MetagenChunkPrepNode(id="p", config=bad).run(
            MetagenChunkPrepConsumes(chunks=CHUNKS, contract=CONTRACT)
        )


async def test_duplicate_target_raises_in_document_prep() -> None:
    dup = MetagenDocumentPrepConfig(
        **_ENDPOINT, targets=[{"field": "summary"}, {"field": "summary"}]
    )
    with pytest.raises(ValueError, match="more than once"):
        await MetagenDocumentPrepNode(id="p", config=dup).run(
            MetagenDocumentPrepConsumes(chunks=CHUNKS, contract=CONTRACT)
        )
