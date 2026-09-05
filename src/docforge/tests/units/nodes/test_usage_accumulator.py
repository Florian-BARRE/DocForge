# ====== Code Summary ======
# Locks UsageAccumulator — the openai_compat seam that attributes the token usage of EVERY paid
# attempt a chat client answers, not just the final success. A node reading ``answer.usage_metadata``
# bills only the last call; a failed-but-usage-bearing attempt (an own-loop retry, or a response the
# node discards) is otherwise lost. These tests prove the accumulator sums across attempts, stays
# None when nothing was billed, reads a real LLMResult, and wires onto the constructed chat client.

# ====== Third-Party Library Imports ======
from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGeneration, LLMResult

# ====== Internal Project Imports ======
from shared_libs.pipelines.nodes.openai_compat import (
    OpenAICompatConfig,
    OpenAICompatHelpers,
    UsageAccumulator,
)


def _cfg() -> OpenAICompatConfig:
    return OpenAICompatConfig(base_url="http://endpoint/v1", model="m")


def test_accumulates_usage_across_attempts() -> None:
    """A failed-but-billed attempt contributes usage: the accumulator SUMS every attempt, not the last.

    The first ``record`` stands in for a paid attempt the node discarded (it billed 100 input tokens
    then failed); the second is the successful retry. Both must be attributed."""
    sink = UsageAccumulator("m")
    sink.record(100, 0)  # a failed-but-usage-bearing attempt
    sink.record(150, 50)  # the successful retry
    usage = sink.usage
    assert usage is not None
    assert usage.model == "m"
    assert usage.prompt_tokens == 250
    assert usage.completion_tokens == 50


def test_empty_accumulator_reports_no_usage() -> None:
    """An accumulator that observed no billed attempt stays None — a free call is never fabricated."""
    assert UsageAccumulator("m").usage is None


async def test_on_llm_end_extracts_and_folds_generation_usage() -> None:
    """on_llm_end reads a chat generation's usage_metadata and folds it into the running total."""
    sink = UsageAccumulator("m")
    message = AIMessage(
        content="answer",
        usage_metadata={"input_tokens": 10, "output_tokens": 5, "total_tokens": 15},
    )
    result = LLMResult(generations=[[ChatGeneration(message=message)]])
    await sink.on_llm_end(result)
    usage = sink.usage
    assert usage is not None
    assert usage.prompt_tokens == 10
    assert usage.completion_tokens == 5


async def test_on_llm_end_ignores_a_usage_less_result() -> None:
    """A result carrying no usage leaves the accumulator empty (a capture miss never raises)."""
    sink = UsageAccumulator("m")
    result = LLMResult(generations=[[ChatGeneration(message=AIMessage(content="answer"))]])
    await sink.on_llm_end(result)
    assert sink.usage is None


def test_chat_client_attaches_the_usage_sink() -> None:
    """A sink passed to ``chat`` is registered as a client callback (the accumulation is wired, live)."""
    sink = UsageAccumulator("m")
    client = OpenAICompatHelpers.chat(_cfg(), usage_sink=sink)
    assert sink in (client.callbacks or [])


def test_chat_client_has_no_callbacks_without_a_sink() -> None:
    """Omitting the sink leaves the client's callbacks untouched (the seam is strictly opt-in)."""
    client = OpenAICompatHelpers.chat(_cfg())
    assert not client.callbacks
