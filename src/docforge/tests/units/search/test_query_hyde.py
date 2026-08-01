"""The HyDE query node: with the provider chat call mocked, it APPENDS the model's hypothetical
passage to the spec's text (so encode embeds the richer text) and stamps token usage; on any provider
failure OR an empty answer it returns the ORIGINAL spec unchanged — the degrade discipline that keeps
an enabled HyDE from ever breaking a search. Also proves the HyDE blob builds + validates and splices
the transform between normalize and encode with all three spec consumers repointed. No network, no
store.
"""

import asyncio

from shared_libs.pipelines.build import PipelineBuilder
from shared_libs.pipelines.search import SearchPipeline
from shared_libs.pipelines.search.nodes.query.hyde.core import QueryHydeNode
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
        text="what is X",
        filters={"year": 2024},
        top_k=5,
        candidate_k=20,
        search_targets=[SearchTarget(field="tags", semantic=True)],
        flags={"boost": True},
    )


def _run(node: QueryHydeNode, data: QuerySpec) -> object:
    """Run the node once on a QuerySpec input."""
    return asyncio.run(node.run(QueryHydeNode.Consumes(spec=data)))


# ---------------------- Node unit tests ---------------------- #
def test_hyde_appends_passage_and_stamps_usage(monkeypatch) -> None:
    """The hypothetical passage is appended to the text; other fields + a usage stamp survive."""
    _install_model(
        monkeypatch,
        _FakeModel(_FakeAnswer("  X is a thing.  ", {"input_tokens": 9, "output_tokens": 7})),
    )
    node = QueryHydeNode(id="hyde", config=QueryHydeNode.Config())

    out = _run(node, _spec())

    # 1. The text is the original followed by the stripped passage; other fields copied through.
    assert out.spec.text == "what is X\n\nX is a thing."
    assert out.spec.filters == {"year": 2024}
    assert out.spec.top_k == 5
    assert out.spec.candidate_k == 20
    assert out.spec.search_targets == [SearchTarget(field="tags", semantic=True)]
    assert out.spec.flags == {"boost": True}
    # 2. Usage is captured from the answer's metadata, keyed by the configured model.
    assert out._usage is not None
    assert out._usage.prompt_tokens == 9
    assert out._usage.completion_tokens == 7
    assert out._usage.model == QueryHydeNode.Config().model


def test_hyde_degrades_to_original_on_provider_error(monkeypatch) -> None:
    """A raising provider call returns the ORIGINAL spec unchanged — never a raise, no usage."""
    _install_model(monkeypatch, _FakeModel(exc=RuntimeError("connection refused")))
    node = QueryHydeNode(id="hyde", config=QueryHydeNode.Config())

    out = _run(node, _spec())

    assert out.spec.text == "what is X"
    assert out._usage is None


def test_hyde_empty_answer_keeps_original(monkeypatch) -> None:
    """A whitespace-only passage degrades to the original query text (the empty-output guard)."""
    _install_model(
        monkeypatch, _FakeModel(_FakeAnswer("   ", {"input_tokens": 3, "output_tokens": 0}))
    )
    node = QueryHydeNode(id="hyde", config=QueryHydeNode.Config())

    out = _run(node, _spec())

    assert out.spec.text == "what is X"


# ---------------------- Blob wiring tests ---------------------- #
def test_hyde_blob_builds_and_validates_clean() -> None:
    """The HyDE blob builds and passes the graph validator with ZERO issues."""
    blob = SearchPipeline.hyde_blob()
    assert [node.id for node in blob.nodes] == [
        "normalize",
        "hyde",
        "encode",
        "retrieve",
        "hydrate",
        "deliver",
    ]
    group = PipelineBuilder().build(blob)
    assert GraphValidator().validate(group) == []


def test_hyde_blob_repoints_every_spec_consumer_onto_the_transform() -> None:
    """encode + retrieve + hydrate all read the HyDE node's spec, not normalize's."""
    bindings = SearchPipeline.hyde_blob().bindings
    assert bindings["hyde"]["spec"].node_id == "normalize"
    for consumer in ("encode", "retrieve", "hydrate"):
        assert bindings[consumer]["spec"].node_id == "hyde", consumer
