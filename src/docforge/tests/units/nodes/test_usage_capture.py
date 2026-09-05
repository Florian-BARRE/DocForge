"""Token-usage capture on paid nodes: an LLM/VLM whose model returns an AIMessage with
``usage_metadata`` stamps the usage (model + tokens) onto the returned output (which the engine
lifts onto the record); a paid embed node folds each embeddings response's ``usage.prompt_tokens``
into the output (``completion_tokens`` 0); a provider that OMITS usage leaves it None with no crash;
and structgen's ``include_raw=True`` rebuild returns the parsed value UNCHANGED while still capturing
usage from the raw message.

The model/endpoint call is faked (no endpoint). Usage rides on the output via the ``_usage`` private
attr — proving the engine-facing seam without running the engine.
"""

import uuid
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock

from langchain_core.messages import AIMessage

from shared_libs.pipelines.nodes.embed.base import EmbedConsumes
from shared_libs.pipelines.nodes.embed.openai_compatible import core as embed_core
from shared_libs.pipelines.nodes.embed.openai_compatible.core import EmbedOpenAICompatibleNode
from shared_libs.pipelines.nodes.llm.base import BaseLlmChatConfig, BaseLlmChatNode
from shared_libs.pipelines.nodes.llm.base.io import LlmChatConsumes
from shared_libs.pipelines.nodes.structgen.base import StructGenConfig, StructGenConsumes
from shared_libs.pipelines.nodes.structgen.openai_compatible import core as structgen_core
from shared_libs.pipelines.nodes.structgen.openai_compatible.core import (
    StructGenOpenAICompatibleNode,
)
from shared_libs.pipelines.nodes.vlm.base import VlmConsumes
from shared_libs.pipelines.nodes.vlm.openai_compatible import core as vlm_core
from shared_libs.pipelines.nodes.vlm.openai_compatible.core import VlmOpenAICompatibleNode
from shared_libs.public_models import (
    Chunk,
    CollectionContract,
    FieldOrigin,
    FieldScope,
    FieldType,
    FigureItem,
    GenerationField,
    GenerationRequest,
    MetadataFieldSpec,
    OpenAICompatConfig,
    Prompt,
)

USAGE = {"input_tokens": 12, "output_tokens": 7, "total_tokens": 19}


def _fake_model(answer: AIMessage) -> MagicMock:
    """A LangChain-model stand-in whose ``ainvoke`` returns ``answer``."""
    model = MagicMock()
    model.ainvoke = AsyncMock(return_value=answer)
    return model


# --------------------------------------------------------------------------- #
# LLM
# --------------------------------------------------------------------------- #


class _FakeLlm(BaseLlmChatNode):
    """A concrete LLM node whose ``_chat_model`` is stubbed per test — never networked."""

    KIND = "test_usage_llm"
    NAME = "F"
    SUMMARY = "t"
    Config = BaseLlmChatConfig

    _model: Any = None

    def _chat_model(self):
        return self._model


def _llm(answer: AIMessage) -> _FakeLlm:
    node = _FakeLlm(
        id="llm", config=BaseLlmChatConfig(base_url="http://x", api_key="k", model="gpt-4o-mini")
    )
    node._model = _fake_model(answer)
    return node


async def test_llm_captures_usage_and_model() -> None:
    node = _llm(AIMessage(content="hello", usage_metadata=USAGE))
    out = await node.run(LlmChatConsumes(prompt=Prompt(messages=[])))

    assert out.completion.text == "hello"
    assert out._usage is not None
    assert out._usage.model == "gpt-4o-mini"
    assert (out._usage.prompt_tokens, out._usage.completion_tokens) == (12, 7)


async def test_llm_without_usage_metadata_stays_none() -> None:
    node = _llm(AIMessage(content="hello", usage_metadata=None))
    out = await node.run(LlmChatConsumes(prompt=Prompt(messages=[])))

    assert out.completion.text == "hello"
    assert out._usage is None


# --------------------------------------------------------------------------- #
# VLM
# --------------------------------------------------------------------------- #


def _vlm(monkeypatch, answer: AIMessage) -> VlmOpenAICompatibleNode:
    """Build a VLM node whose chat client folds the answer's usage into the passed sink.

    The live capture rides on the LangChain ``on_llm_end`` callback (the ``usage_sink`` the node
    threads across its retry loop); a bare AsyncMock never fires it, so the fake ``chat`` records the
    answer's usage into the sink itself — standing in for the callback the real client would fire.
    """

    def _chat(*args, usage_sink=None, **kwargs):
        model = _fake_model(answer)
        meta = answer.usage_metadata
        if usage_sink is not None and meta is not None:
            usage_sink.record(meta["input_tokens"], meta["output_tokens"])
        return model

    monkeypatch.setattr(vlm_core.OpenAICompatHelpers, "chat", _chat)
    return VlmOpenAICompatibleNode(
        id="vlm",
        config=vlm_core.VlmOpenAICompatibleConfig(base_url="http://x", model="gpt-4o", api_key="k"),
    )


async def test_vlm_captures_usage(monkeypatch) -> None:
    node = _vlm(monkeypatch, AIMessage(content="a chart", usage_metadata=USAGE))
    out = await node.run(VlmConsumes(figure=FigureItem(block_id="f", image=b"png", read_text="")))

    assert out.entry.description == "a chart"
    assert out._usage is not None
    assert out._usage.model == "gpt-4o"
    assert (out._usage.prompt_tokens, out._usage.completion_tokens) == (12, 7)


async def test_vlm_without_usage_metadata_stays_none(monkeypatch) -> None:
    node = _vlm(monkeypatch, AIMessage(content="a chart", usage_metadata=None))
    out = await node.run(VlmConsumes(figure=FigureItem(block_id="f", image=b"png", read_text="")))

    assert out._usage is None


# --------------------------------------------------------------------------- #
# embed — a paid endpoint folds its response usage (input tokens only) onto the output
# --------------------------------------------------------------------------- #

_EMBED_CONTRACT = CollectionContract(
    collection_id=uuid.uuid4(),
    name="c",
    supported_formats=["pdf"],
    max_file_size_bytes=1,
    fields=[],
)
_EMBED_CHUNKS = [
    Chunk(chunk_id="d#c0", ordinal=0, text="Cats purr."),
    Chunk(chunk_id="d#c1", ordinal=1, text="Dogs bark."),
]


def _fake_embeddings_client(usage: object) -> MagicMock:
    """An OpenAIEmbeddings stand-in whose ``async_client.create`` returns one vector per input.

    The response mirrors an OpenAI-compatible embeddings payload: ``data`` (index + embedding) and a
    single ``usage`` object carrying ``prompt_tokens`` for the whole batch.
    """

    async def _create(input: list[str], model: str, **_: object) -> SimpleNamespace:  # noqa: A002
        data = [SimpleNamespace(index=i, embedding=[float(i)]) for i in range(len(input))]
        return SimpleNamespace(data=data, usage=usage)

    client = MagicMock()
    client.async_client = SimpleNamespace(create=_create)
    return client


def _embed_node(monkeypatch, usage: object) -> EmbedOpenAICompatibleNode:
    monkeypatch.setattr(
        embed_core.OpenAICompatHelpers,
        "embeddings",
        lambda *a, **k: _fake_embeddings_client(usage),
    )
    return EmbedOpenAICompatibleNode(
        id="embed",
        config=embed_core.EmbedOpenAICompatibleConfig(
            base_url="http://x", api_key="k", model="text-embedding-3-small"
        ),
    )


async def test_embed_captures_input_tokens_as_usage(monkeypatch) -> None:
    node = _embed_node(monkeypatch, SimpleNamespace(prompt_tokens=42, total_tokens=42))
    out = await node.run(EmbedConsumes(chunks=_EMBED_CHUNKS, contract=_EMBED_CONTRACT))

    assert len(out.embeddings.items) == 2
    assert out._usage is not None
    assert out._usage.model == "text-embedding-3-small"
    # An embedding call bills input tokens only — completion is 0.
    assert (out._usage.prompt_tokens, out._usage.completion_tokens) == (42, 0)


async def test_embed_without_usage_stays_none(monkeypatch) -> None:
    node = _embed_node(monkeypatch, None)  # endpoint omitted usage
    out = await node.run(EmbedConsumes(chunks=_EMBED_CHUNKS, contract=_EMBED_CONTRACT))

    assert len(out.embeddings.items) == 2  # still emits vectors — a usage miss never fails the node
    assert out._usage is None


# --------------------------------------------------------------------------- #
# structgen — include_raw keeps the parsed value while surfacing usage
# --------------------------------------------------------------------------- #


def _structgen_request() -> GenerationRequest:
    spec = MetadataFieldSpec(
        field_name="year",
        field_type=FieldType.INTEGER,
        origin=FieldOrigin.GENERATED,
        scope=FieldScope.DOCUMENT,
    )
    return GenerationRequest(
        request_id="r0",
        chunk_id="d#c0",
        system_prompt="Extract.",
        text="Published in 2024.",
        fields=[GenerationField(spec=spec, instruction="Fill year.")],
        endpoint=OpenAICompatConfig(base_url="http://req", model="gpt-4.1-mini"),
        temperature=0.0,
        max_tokens=64,
    )


def _structured_model(parsed: dict, raw: AIMessage) -> MagicMock:
    """A model whose with_structured_output(..., include_raw=True) yields {"raw", "parsed"}."""
    structured = MagicMock()
    structured.ainvoke = AsyncMock(return_value={"raw": raw, "parsed": parsed})
    model = MagicMock()
    model.with_structured_output = MagicMock(return_value=structured)
    return model


async def test_structgen_include_raw_keeps_parsed_and_captures_usage(monkeypatch) -> None:
    raw = AIMessage(content="", usage_metadata=USAGE)
    captured: dict[str, object] = {}

    def _chat(*args, **kwargs):
        model = _structured_model({"year": 2024}, raw)
        original = model.with_structured_output

        def _wso(schema, include_raw=False):
            captured["include_raw"] = include_raw
            return original(schema, include_raw=include_raw)

        model.with_structured_output = _wso
        return model

    monkeypatch.setattr(structgen_core.OpenAICompatHelpers, "chat", _chat)

    node = StructGenOpenAICompatibleNode(id="s", config=StructGenConfig())
    out = await node.run(StructGenConsumes(request=_structgen_request()))

    # The rebuild passed include_raw=True and the parsed value coerced unchanged (2024 -> int).
    assert captured["include_raw"] is True
    assert out.values.values == {"year": 2024}
    # Usage was lifted from the raw message onto the output, stamped with the effective model.
    assert out._usage is not None
    assert out._usage.model == "gpt-4.1-mini"
    assert (out._usage.prompt_tokens, out._usage.completion_tokens) == (12, 7)
