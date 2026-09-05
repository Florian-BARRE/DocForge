"""The openai_compat client factory must not STACK retries: a node that owns a TimeoutRetryConfig
loop (VLM, embed) leaves the factory's max_retries unpinned, and the factory then hands the openai
SDK client max_retries=0 — so the node's loop is the ONLY retry layer. Left at the SDK's silent
default of 2, an outage would multiply (e.g. 3×3). A consumer with no own loop (llm/structgen/ocr/
classify) pins a value and the factory delegates retries to the SDK unchanged.
"""

from shared_libs.pipelines.nodes.openai_compat import OpenAICompatConfig, OpenAICompatHelpers


def _cfg() -> OpenAICompatConfig:
    return OpenAICompatConfig(base_url="http://endpoint/v1", model="m")


def test_chat_client_disables_the_sdk_retries_when_unpinned() -> None:
    """An unpinned chat client kills the SDK's built-in retries (the node loop governs alone)."""
    client = OpenAICompatHelpers.chat(_cfg())
    assert client.max_retries == 0


def test_embeddings_client_disables_the_sdk_retries_when_unpinned() -> None:
    """Same for embeddings — the embed node owns a retry + batch-split loop, no SDK doubling."""
    client = OpenAICompatHelpers.embeddings(_cfg())
    assert client.max_retries == 0


def test_chat_client_honors_a_pinned_retry_count() -> None:
    """A consumer with no own loop (llm/structgen/classify) delegates retries to the SDK."""
    client = OpenAICompatHelpers.chat(_cfg(), max_retries=4)
    assert client.max_retries == 4


def test_embeddings_client_honors_a_pinned_retry_count() -> None:
    """chunk/semantic pins its embed retries — the factory forwards the value unchanged."""
    client = OpenAICompatHelpers.embeddings(_cfg(), max_retries=3)
    assert client.max_retries == 3
