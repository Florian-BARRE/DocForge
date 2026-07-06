# ====== Code Summary ======
# Live-suite bootstrap: probes the real API (http://127.0.0.1:8000) and the compose stores
# (postgres/redis/qdrant/s3 on 10041-10044) once per session, auto-skipping the whole suite when
# the stack is not reachable. Every test in tests/live/ is marked ``live`` (see pytest.ini).

# ====== Standard Library Imports ======
import socket

# ====== Third-Party Library Imports ======
import httpx
import pytest

API_BASE_URL = "http://127.0.0.1:8000"
STORE_PORTS = {"postgres": 10041, "redis": 10042, "qdrant": 10043, "s3": 10044}


def _tcp_open(host: str, port: int, timeout: float = 1.0) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def _api_reachable() -> bool:
    try:
        response = httpx.get(f"{API_BASE_URL}/api/v1/pipelines", timeout=2.0)
        return response.status_code == 200
    except httpx.HTTPError:
        return False


def pytest_collection_modifyitems(config, items) -> None:
    """Mark every collected test in tests/live/ with the 'live' marker automatically."""
    for item in items:
        item.add_marker(pytest.mark.live)


@pytest.fixture(scope="session", autouse=True)
def _skip_if_stack_down() -> None:
    stores_down = [name for name, port in STORE_PORTS.items() if not _tcp_open("127.0.0.1", port)]
    api_up = _api_reachable()
    if stores_down or not api_up:
        pytest.skip(
            f"live stack unreachable (api_up={api_up}, stores_down={stores_down}) — skipping tests/live"
        )


@pytest.fixture(scope="session")
def api_client() -> httpx.Client:
    """An httpx client bound to the real running API."""
    with httpx.Client(base_url=API_BASE_URL, timeout=30.0) as client:
        yield client
