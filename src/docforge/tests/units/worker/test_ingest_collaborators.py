"""The ``jobs.ingest`` collaborators on their own: the cache-hook rule, the runner kwargs of the two
run modes, the shared translation (strategy + config hash) and the replay failure marking. The whole
``ingest_document`` lifecycle is pinned by test_jobs_core.py and the characterization call-order net."""

import hashlib
import json
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock


def _services(ingest, **config):
    runtime = SimpleNamespace(
        WORKER_CACHE_ENABLED=config.get("cache", True),
        WORKER_PREFLIGHT_ENABLED=True,
        WORKER_PREFLIGHT_CACHE_TTL_SECONDS=0.0,
        PROVIDER_EGRESS_ALLOWLIST="",
    )
    return ingest.IngestServices(
        database=SimpleNamespace(),
        s3=None,
        runner=SimpleNamespace(run=AsyncMock(return_value=("bundle", "record"))),
        config=runtime,
        logger=MagicMock(),
        worker_id="w1",
        job_timeout_seconds=30.0,
    )


def test_services_are_read_off_the_context(jobs_core) -> None:
    from jobs.ingest import IngestServices  # noqa: PLC0415

    context = SimpleNamespace(
        database="db",
        s3="s3",
        runner="runner",
        RUNTIME_CONFIG="config",
        logger="log",
        worker_id="w9",
        job_timeout_seconds=12.0,
    )

    services = IngestServices.from_context(context)

    assert (services.database, services.config, services.worker_id) == ("db", "config", "w9")


def test_cache_hook_is_built_only_when_enabled_and_not_forced(jobs_core) -> None:
    import jobs.ingest as ingest  # noqa: PLC0415

    factory = MagicMock(return_value="hook")
    executor = ingest.RunExecutor(_services(ingest), factory)
    collection_id, doc_id = uuid.uuid4(), uuid.uuid4()

    assert executor.build_cache_hook({"nodes": []}, collection_id, doc_id, force=False) == "hook"
    assert executor.build_cache_hook({"nodes": []}, collection_id, doc_id, force=True) is None
    factory.assert_called_once()  # forced run: the factory is never called
    disabled = ingest.RunExecutor(_services(ingest, cache=False), factory)
    assert disabled.build_cache_hook({"nodes": []}, collection_id, doc_id, force=False) is None


async def test_full_run_hands_the_cache_hook_and_replay_the_resume_point(jobs_core) -> None:
    import jobs.ingest as ingest  # noqa: PLC0415

    services = _services(ingest)
    executor = ingest.RunExecutor(services, MagicMock())
    common = {
        "timeout_seconds": 5.0,
        "progress_callback": "cb",
        "trace_level": "lvl",
    }

    await executor.run_full({}, "src", "contract", cache_hook=None, document_id="d", **common)
    await executor.run_replay({}, "src", "contract", resume="resume", **common)

    full_kwargs, replay_kwargs = (call.kwargs for call in services.runner.run.await_args_list)
    assert "cache_hook" in full_kwargs and "resume" not in full_kwargs
    assert "resume" in replay_kwargs and "cache_hook" not in replay_kwargs


def test_translation_derives_the_chunker_strategy_and_the_full_config_hash(
    jobs_core, monkeypatch
) -> None:
    from jobs.ingest import Persister  # noqa: PLC0415

    translate = MagicMock(return_value="translated")
    monkeypatch.setattr("jobs.ingest.persister.RunTranslator.translate", translate)
    blob = {
        "nodes": [{"id": "a", "family": "parser"}, {"id": "b", "family": "chunker", "kind": "k"}]
    }
    doc_id = uuid.uuid4()

    assert Persister.translate(doc_id, "bundle", ["schema"], blob) == "translated"

    expected_hash = hashlib.sha256(
        json.dumps(blob, sort_keys=True, default=str).encode()
    ).hexdigest()
    translate.assert_called_once_with(doc_id, "bundle", ["schema"], "k", expected_hash)


async def test_a_failed_replay_keeps_the_document_status_and_only_warns(jobs_core) -> None:
    from jobs.ingest import FailureHandler  # noqa: PLC0415

    ingestion = SimpleNamespace(mark_failed=AsyncMock(), mark_replay_failed=AsyncMock())
    services = SimpleNamespace(database=SimpleNamespace(ingestion=ingestion), logger=MagicMock())
    handler = FailureHandler(services)
    doc_id = uuid.uuid4()

    await handler.mark_document_failed(doc_id, "chunk", "boom")
    await handler.mark_document_failed(doc_id, None, "boom")

    ingestion.mark_failed.assert_awaited_once_with(doc_id)
    warning = ingestion.mark_replay_failed.await_args.args[1]
    assert "Replay from 'chunk' failed (boom)" in warning
