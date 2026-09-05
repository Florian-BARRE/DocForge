"""The LLM query-rewrite node: with the provider chat call mocked, it replaces ONLY the spec's text
with the model's rewrite (every other field copied through) and stamps token usage; on any provider
failure OR an empty answer it returns the ORIGINAL spec unchanged — the degrade discipline that keeps
an enabled rewrite from ever breaking a search. Also proves the rewrite blob builds + validates and
splices the transform between normalize and encode with all three spec consumers repointed. No
network, no store.
"""

import asyncio

from shared_libs.pipelines.build import PipelineBuilder
from shared_libs.pipelines.search import SearchPipeline
from shared_libs.pipelines.search.nodes.query.rewrite.core import QueryRewriteNode
from shared_libs.pipelines.validation import GraphValidator
from shared_libs.public_models.search import QuerySpec, SearchTarget


# ---------------------- Test doubles ---------------------- #
class _FakeAnswer:
    """A stand-in LangChain AIMessage carrying content + optional usage metadata."""

    def __init__(self, content: str, usage_metadata: dict | None = None) -> None:
        self.content = content
        self.usage_metadata = usage_metadata


class _FakeModel:
    """A stand-in chat model: returns a fixed answer or raises a fixed exception on ainvoke."""

    def __init__(self, answer: _FakeAnswer | None = None, exc: Exception | None = None) -> None:
        self._answer = answer
        self._exc = exc

    async def ainvoke(self, messages: object) -> _FakeAnswer:
        """Return the canned answer, or raise the canned provider error."""
        if self._exc is not None:
            raise self._exc
        return self._answer


def _install_model(monkeypatch, model: _FakeModel) -> None:
    """Patch the shared factory so the node's provider call is a pure function (no network)."""
    monkeypatch.setattr(
        "shared_libs.pipelines.search.nodes.query.base.OpenAICompatHelpers.chat",
        lambda *args, **kwargs: model,
    )


def _spec() -> QuerySpec:
    """A spec with every field populated, so the passthrough of the non-text fields is provable."""
    return QuerySpec(
        text="orig query",
        filters={"year": 2024},
        top_k=5,
        candidate_k=20,
        search_targets=[SearchTarget(field="tags", semantic=True)],
        flags={"boost": True},
    )


def _run(node: QueryRewriteNode, data: QuerySpec) -> object:
    """Run the node once on a QuerySpec input."""
    return asyncio.run(node.run(QueryRewriteNode.Consumes(spec=data)))


# ---------------------- Node unit tests ---------------------- #
def test_rewrite_replaces_text_and_stamps_usage(monkeypatch) -> None:
    """A returned rewrite replaces only the text; all other fields + a usage stamp survive."""
    _install_model(
        monkeypatch,
        _FakeModel(_FakeAnswer("  better query  ", {"input_tokens": 12, "output_tokens": 4})),
    )
    node = QueryRewriteNode(id="rewrite", config=QueryRewriteNode.Config())

    out = _run(node, _spec())

    # 1. Only the text changed (stripped); every other field copied through untouched.
    assert out.spec.text == "better query"
    assert out.spec.filters == {"year": 2024}
    assert out.spec.top_k == 5
    assert out.spec.candidate_k == 20
    assert out.spec.search_targets == [SearchTarget(field="tags", semantic=True)]
    assert out.spec.flags == {"boost": True}
    # 2. Usage is captured from the answer's metadata, keyed by the configured model.
    assert out._usage is not None
    assert out._usage.prompt_tokens == 12
    assert out._usage.completion_tokens == 4
    assert out._usage.model == QueryRewriteNode.Config().model


def test_rewrite_degrades_to_original_on_provider_error(monkeypatch) -> None:
    """A raising provider call returns the ORIGINAL spec unchanged — never a raise, no usage."""
    _install_model(monkeypatch, _FakeModel(exc=TimeoutError()))
    node = QueryRewriteNode(id="rewrite", config=QueryRewriteNode.Config())

    spec = _spec()
    out = _run(node, spec)

    assert out.spec.text == "orig query"
    assert out.spec.filters == {"year": 2024}
    assert out._usage is None


def test_rewrite_empty_answer_keeps_original(monkeypatch) -> None:
    """A whitespace-only rewrite degrades to the original query text (the empty-output guard)."""
    _install_model(
        monkeypatch, _FakeModel(_FakeAnswer("   \n  ", {"input_tokens": 3, "output_tokens": 0}))
    )
    node = QueryRewriteNode(id="rewrite", config=QueryRewriteNode.Config())

    out = _run(node, _spec())

    assert out.spec.text == "orig query"


def test_provider_failure_stamps_a_visible_degrade_flag(monkeypatch) -> None:
    """A provider failure degrades to the raw query AND stamps a degrade notice into spec.flags.

    The notice rides downstream (encode folds it into SearchResult.debug) so the fallback is VISIBLE
    to the caller instead of a silent swap to the un-transformed query.
    """
    from shared_libs.pipelines.search.nodes.query.base import QUERY_DEGRADED_FLAG  # noqa: PLC0415

    _install_model(monkeypatch, _FakeModel(exc=TimeoutError()))
    node = QueryRewriteNode(id="rewrite", config=QueryRewriteNode.Config())

    out = _run(node, _spec())

    # 1. The pre-existing flag survives (additive) and the degrade notice is present + names the kind.
    assert out.spec.flags["boost"] is True
    assert "rewrite" in out.spec.flags[QUERY_DEGRADED_FLAG]
    assert "raw query used" in out.spec.flags[QUERY_DEGRADED_FLAG]


def test_successful_rewrite_stamps_no_degrade_flag(monkeypatch) -> None:
    """A healthy rewrite leaves flags untouched — the degrade notice appears ONLY on degrade."""
    from shared_libs.pipelines.search.nodes.query.base import QUERY_DEGRADED_FLAG  # noqa: PLC0415

    _install_model(monkeypatch, _FakeModel(_FakeAnswer("better query")))
    node = QueryRewriteNode(id="rewrite", config=QueryRewriteNode.Config())

    out = _run(node, _spec())

    assert QUERY_DEGRADED_FLAG not in out.spec.flags
    assert out.spec.flags == {"boost": True}


# ---------------------- Blob wiring tests ---------------------- #
def test_rewrite_blob_builds_and_validates_clean() -> None:
    """The rewrite blob builds and passes the graph validator with ZERO issues."""
    blob = SearchPipeline.rewrite_blob()
    assert [node.id for node in blob.nodes] == [
        "normalize",
        "rewrite",
        "encode",
        "retrieve",
        "hydrate",
        "deliver",
    ]
    group = PipelineBuilder().build(blob)
    assert GraphValidator().validate(group) == []


def test_rewrite_blob_repoints_every_spec_consumer_onto_the_transform() -> None:
    """encode + retrieve + hydrate all read the rewrite node's spec, not normalize's."""
    bindings = SearchPipeline.rewrite_blob().bindings
    assert bindings["rewrite"]["spec"].node_id == "normalize"
    for consumer in ("encode", "retrieve", "hydrate"):
        assert bindings[consumer]["spec"].node_id == "rewrite", consumer
