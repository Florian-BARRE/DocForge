"""Phase 2 C — the human-readable names surfaced on the job responses.

The jobs list + single GET join the job row to its document filename and collection name at read
(no denormalised column). These tests prove the two routes carry those names — plus the current
stage and the cancel_requested flag — onto the JobStatus model, with CONTEXT.database mocked.
"""

import uuid
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

COLL_A = "11111111-1111-1111-1111-111111111111"


def _full():
    from backend.libs.auth.principal import AuthPrincipal  # noqa: PLC0415

    key = SimpleNamespace(permissions=None, revoked_at=None, user_id="user-1")
    return AuthPrincipal(user=SimpleNamespace(is_active=True), key=key, is_full_access=True)


def _job(*, cancel_requested=False):
    from shared_libs.services.db.postgresql.tables import JobKind, JobStatus  # noqa: PLC0415

    return SimpleNamespace(
        id=uuid.uuid4(),
        document_id=uuid.uuid4(),
        collection_id=uuid.UUID(COLL_A),
        status=JobStatus.RUNNING,
        kind=JobKind.INGEST,
        cancel_requested=cancel_requested,
        progress=40,
        current_stage="chunk",
        error=None,
        attempt=1,
        started_at=None,
        finished_at=None,
        updated_at=datetime(2026, 8, 3, 12, 0, tzinfo=UTC),
        total_prompt_tokens=0,
        total_completion_tokens=0,
        cost_usd=0,
        items_done=None,
        items_total=None,
        failed_node_id=None,
        failed_node_kind=None,
        failed_item_index=None,
        error_type=None,
    )


def _with_names(
    job,
    filename="contract.pdf",
    collection_name="legal",
    title="Master Agreement",
    display_title="MSA 2026 — Acme",
):
    return SimpleNamespace(
        job=job,
        document_filename=filename,
        document_title=title,
        collection_name=collection_name,
        document_display_title=display_title,
    )


async def test_list_jobs_carries_filename_collection_name_and_stage(
    fastapi_app, monkeypatch
) -> None:
    from backend.context import CONTEXT  # noqa: PLC0415
    from backend.routers.jobs.router import list_jobs  # noqa: PLC0415

    entry = _with_names(_job(cancel_requested=True))
    jobs = SimpleNamespace(
        list_jobs_with_names=AsyncMock(return_value=[entry]),
        count_jobs=AsyncMock(return_value=1),
    )
    monkeypatch.setattr(CONTEXT, "database", SimpleNamespace(jobs=jobs), raising=False)

    result = await list_jobs(
        collection_id=uuid.UUID(COLL_A),
        status=None,
        order="newest",
        limit=500,
        offset=0,
        principal=_full(),
    )

    # The list is now a paginated envelope: total + limit/offset echo + the page of jobs.
    assert result.total == 1
    row = result.jobs[0]
    assert row.document_filename == "contract.pdf"
    assert row.document_title == "Master Agreement"
    assert row.display_title == "MSA 2026 — Acme"
    assert row.collection_name == "legal"
    assert row.current_stage == "chunk"
    assert row.cancel_requested is True


async def test_get_job_carries_filename_and_collection_name(fastapi_app, monkeypatch) -> None:
    from backend.context import CONTEXT  # noqa: PLC0415
    from backend.routers.jobs.router import get_job  # noqa: PLC0415

    entry = _with_names(_job())
    jobs = SimpleNamespace(get_with_names=AsyncMock(return_value=entry))
    monkeypatch.setattr(CONTEXT, "database", SimpleNamespace(jobs=jobs), raising=False)

    result = await get_job(job_id=entry.job.id, principal=_full())

    assert result.document_filename == "contract.pdf"
    assert result.document_title == "Master Agreement"
    assert result.display_title == "MSA 2026 — Acme"
    assert result.collection_name == "legal"
    assert result.current_stage == "chunk"


def test_row_to_names_resolves_the_display_title_from_the_title_field_value() -> None:
    """The joined row's title_field value wins over the parsed title; blank/unset falls back to it;
    an empty parsed title with no title_field surfaces None (never a blank label)."""
    from shared_libs.services.db.postgresql.apis.job_api import JobApi  # noqa: PLC0415

    job = SimpleNamespace(id=uuid.uuid4())
    by_field = JobApi._row_to_names((job, "a.pdf", "1 GENERALITES", "c", "doc_title", "Real Title"))
    assert by_field.document_display_title == "Real Title"
    assert by_field.document_title == "1 GENERALITES"

    listed = JobApi._row_to_names((job, "a.pdf", "Parsed", "c", "authors", ["Ada", " ", "Alan"]))
    assert listed.document_display_title == "Ada, Alan"

    blank = JobApi._row_to_names((job, "a.pdf", "Parsed", "c", "doc_title", "   "))
    assert blank.document_display_title == "Parsed"

    unset = JobApi._row_to_names((job, "a.pdf", "Parsed", "c", None, None))
    assert unset.document_display_title == "Parsed"

    untitled = JobApi._row_to_names((job, "a.pdf", "", "c", None, None))
    assert untitled.document_title is None and untitled.document_display_title is None


def test_with_names_select_is_one_statement_with_a_correlated_title_value() -> None:
    """The display title rides in the SAME select as the job page (a correlated scalar subquery),
    never a per-row read — the compiled SQL carries the title_field join + document_metadata seek."""
    from sqlalchemy.dialects import postgresql  # noqa: PLC0415

    from shared_libs.services.db.postgresql.apis.job_api import JobApi  # noqa: PLC0415

    sql = str(JobApi._with_names_select().compile(dialect=postgresql.dialect()))
    assert sql.count("SELECT") == 2  # the page select + the one correlated scalar subquery
    assert "collection.title_field" in sql
    assert "document_metadata.document_id = job.document_id" in sql
