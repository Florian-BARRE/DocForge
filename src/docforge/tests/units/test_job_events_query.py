"""JobApi.events_query — the lean vs full stage-event SELECT (W1-12).

The polled job timeline (the live SSE stream's per-tick delta) never renders the two wide JSONB shape
summaries — they exist only at the run's end and are shown on node-expand. So the hot poll path defers
``input_summary``/``output_summary`` OUT of the SELECT (``include_summaries=False``) and Postgres never
reads or de-TOASTs them; the one-shot trace read keeps them. This asserts the rendered column set of
each variant without a live DB (compile against the Postgres dialect)."""

import uuid

from sqlalchemy.dialects import postgresql

from shared_libs.services.db.postgresql.apis.job_api import JobApi

_JOB_ID = uuid.UUID("11111111-1111-1111-1111-111111111111")


def _compiled(include_summaries: bool) -> str:
    stmt = JobApi.events_query(_JOB_ID, include_summaries=include_summaries)
    return str(stmt.compile(dialect=postgresql.dialect()))


def test_full_query_selects_the_summaries() -> None:
    """The default (full) trace read still selects both JSONB shape summaries."""
    sql = _compiled(include_summaries=True)
    assert "input_summary" in sql
    assert "output_summary" in sql


def test_lean_query_defers_only_the_summaries() -> None:
    """The lean poll query omits BOTH summary columns while keeping the flat timeline columns."""
    sql = _compiled(include_summaries=False)
    assert "input_summary" not in sql
    assert "output_summary" not in sql
    # The flat timeline the stream renders is untouched.
    for column in ("node_path", "stage", "status", "node_kind", "score", "depth", "item_index"):
        assert column in sql, column
