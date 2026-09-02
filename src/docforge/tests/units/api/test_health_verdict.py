"""HealthVerdictResolver — the pure roll-up of a collection's raw health signals into the five
honest states (operational / empty / degraded / ingest_unavailable / down) plus a human reason.
Lightweight stand-ins match the `.family`/`.status`/`.side`/`.kind`/`.detail` reads of a
ProviderProbeResult. ``from backend...`` deferred until fastapi_app registered app/ on sys.path."""

from types import SimpleNamespace


def _probe(family, status, side="ingest", kind="bge_server", detail="boom") -> SimpleNamespace:
    return SimpleNamespace(family=family, status=status, side=side, kind=kind, detail=detail)


def _ok_embedder(side="search") -> SimpleNamespace:
    from shared_libs.pipelines.reachability import ProbeStatus  # noqa: PLC0415

    return _probe("embed", ProbeStatus.OK, side=side)


def _down(family, side="ingest") -> SimpleNamespace:
    from shared_libs.pipelines.reachability import ProbeStatus  # noqa: PLC0415

    return _probe(family, ProbeStatus.UNREACHABLE, side=side)


def test_empty_collection_is_neutral_not_degraded(fastapi_app) -> None:
    from backend.libs.health import HealthVerdict, HealthVerdictResolver  # noqa: PLC0415

    rollup = HealthVerdictResolver.overall(
        ingest_buildable=True,
        search_buildable=True,
        ingest_providers=[],
        search_providers=[_ok_embedder()],
        vector_count=0,
    )
    assert rollup.verdict is HealthVerdict.EMPTY
    assert "ready to ingest" in rollup.reason.lower()


def test_operational_when_index_present_and_all_reachable(fastapi_app) -> None:
    from backend.libs.health import HealthVerdict, HealthVerdictResolver  # noqa: PLC0415

    rollup = HealthVerdictResolver.overall(
        ingest_buildable=True,
        search_buildable=True,
        ingest_providers=[],
        search_providers=[_ok_embedder()],
        vector_count=42,
    )
    assert rollup.verdict is HealthVerdict.OPERATIONAL
    assert "42" in rollup.reason


def test_invalid_ingest_but_working_search_is_ingest_unavailable_not_down(fastapi_app) -> None:
    # The demo case: a structurally invalid ingest blob, but the index exists and search works →
    # ingestion is unavailable, NOT a global outage, and the reason must be human (no raw engine text).
    from backend.libs.health import HealthVerdict, HealthVerdictResolver  # noqa: PLC0415

    rollup = HealthVerdictResolver.overall(
        ingest_buildable=False,
        search_buildable=True,
        ingest_providers=[],
        search_providers=[_ok_embedder()],
        vector_count=17,
    )
    assert rollup.verdict is HealthVerdict.INGEST_UNAVAILABLE
    assert "cannot be ingested" in rollup.reason.lower()
    assert "search over the already-indexed documents still works" in rollup.reason.lower()
    assert "missing_binding" not in rollup.reason  # no raw engine jargon in the first line


def test_down_when_query_embedder_unreachable(fastapi_app) -> None:
    from backend.libs.health import HealthVerdict, HealthVerdictResolver  # noqa: PLC0415

    rollup = HealthVerdictResolver.overall(
        ingest_buildable=True,
        search_buildable=True,
        ingest_providers=[],
        search_providers=[_down("embed", side="search")],
        vector_count=5,
    )
    assert rollup.verdict is HealthVerdict.DOWN
    assert "search is unavailable" in rollup.reason.lower()


def test_down_when_search_graph_unbuildable(fastapi_app) -> None:
    from backend.libs.health import HealthVerdict, HealthVerdictResolver  # noqa: PLC0415

    rollup = HealthVerdictResolver.overall(
        ingest_buildable=True,
        search_buildable=False,
        ingest_providers=[],
        search_providers=[],
        vector_count=5,
    )
    assert rollup.verdict is HealthVerdict.DOWN


def test_degraded_when_an_ingest_provider_is_unreachable(fastapi_app) -> None:
    # Both graphs build and search serves, but a used ingest provider (e.g. a VLM) is unreachable →
    # a real runtime fault worth surfacing, but not down (search still works).
    from backend.libs.health import HealthVerdict, HealthVerdictResolver  # noqa: PLC0415

    rollup = HealthVerdictResolver.overall(
        ingest_buildable=True,
        search_buildable=True,
        ingest_providers=[_down("vlm", side="ingest")],
        search_providers=[_ok_embedder()],
        vector_count=9,
    )
    assert rollup.verdict is HealthVerdict.DEGRADED
    assert "unreachable" in rollup.reason.lower()
    assert "ingest" in rollup.reason.lower()
