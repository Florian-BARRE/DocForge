"""Node-test fixtures.

The network nodes share a process-wide ``HttpClientPool`` (pooled httpx clients keyed by connection
identity). That pool is global state: a client cached by one test would be reused by the next test
with the same endpoint, so a monkeypatched ``httpx.AsyncClient`` in the second test would never be
constructed. Reset the pool before every test to keep each test isolated — the reuse semantics are
proved explicitly in ``test_http_pool.py`` (two calls WITHIN one test → one construction).
"""

import pytest

from shared_libs.pipelines.nodes.http_pool import HttpClientPool


@pytest.fixture(autouse=True)
def _reset_http_pool() -> None:
    """Drop every cached pooled client before each node test (test isolation)."""
    HttpClientPool.reset()
