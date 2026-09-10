"""Node-test fixtures.

The network nodes share two process-wide client pools keyed by connection identity — ``HttpClientPool``
(pooled httpx clients) and ``LangChainClientPool`` (pooled ChatOpenAI/OpenAIEmbeddings). Those pools are
global state: a client cached by one test would be reused by the next test with the same endpoint, so a
monkeypatched client in the second test would never be constructed. Reset both before every test to
keep each test isolated — the reuse semantics are proved explicitly in ``test_http_pool.py`` and
``test_langchain_client_pool.py`` (two calls WITHIN one test → one construction).
"""

import pytest

from shared_libs.pipelines.nodes.http_pool import HttpClientPool
from shared_libs.pipelines.nodes.openai_compat import LangChainClientPool


@pytest.fixture(autouse=True)
def _reset_client_pools() -> None:
    """Drop every cached pooled client before each node test (test isolation)."""
    HttpClientPool.reset()
    LangChainClientPool.reset()
