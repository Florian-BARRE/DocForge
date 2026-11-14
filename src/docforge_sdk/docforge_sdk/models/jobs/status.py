# ====== Code Summary ======
# Job models: the live ingestion status of one job and a bounded, paginated page of them.

# ====== Standard Library Imports ======
from datetime import datetime

# ====== Third-Party Library Imports ======
from pydantic import BaseModel, Field


class JobStatus(BaseModel):
    """
    One ingestion job's live state — written by the worker, only read here.

    Attributes:
        job_id (str): The job row's UUID.
        document_id (str | None): The document being ingested (None for a rebuild_index job).
        document_filename (str | None): The document's filename, joined at read (None if the
            document is gone).
        document_title (str | None): The document's metagen-generated title, joined at read — a
            nicer display label than the filename when present (None if none was generated or the
            document is gone; the UI falls back to document_filename).
        display_title (str | None): The document's display title — the collection's
            ``title_field`` value when configured and set, else the parsed title (None when
            neither exists, the document is gone, or on the SSE stream).
        collection_id (str): Its collection.
        collection_name (str | None): The collection's name, joined at read (None if the
            collection is gone).
        status (str): queued / running / done / failed / cancelled.
        replay_from (str | None): The stage an ingest job replays from (None = a full run).
        cancel_requested (bool): A cooperative stop has been requested; the running job stops at
            its next stage boundary (still 'running' until it does).
        progress (int): 0–100 (completed pipeline nodes over total).
        current_stage (str | None): The node currently (or last) executed.
        error (str | None): The failure, verbatim — only set when status is failed.
        attempt (int): arq retry attempt (1 = first run).
        started_at (datetime | None): When the worker picked it up.
        finished_at (datetime | None): When it ended (done or failed).
        items_done (int | None): Child items finished in the current fan-out stage (None off it).
        items_total (int | None): The current fan-out stage's width (None when not in a fan-out).
        failed_node_id (str | None): The deepest node that raised — only set on a failed job.
        failed_node_kind (str | None): That node's kind/family label — only set on a failed job.
        failed_item_index (int | None): The fan-out item index the failure sits in (None outside one).
        error_type (str | None): Structured cause of the failure — usually the raising exception's
            class name (e.g. "TimeoutError"), plus the reaper's attributed "worker_killed" (process
            lost — crash/OOM) and "job_timeout_exceeded" (a stage wedged past the job timeout on a
            live worker).
    """

    job_id: str = Field(description="The job row's UUID.")
    document_id: str | None = Field(
        description="The document being ingested; null for a collection-level job (rebuild_index)."
    )
    document_filename: str | None = Field(
        default=None,
        description="The document's filename, joined at read (None if the document is gone).",
    )
    document_title: str | None = Field(
        default=None,
        description="The document's metagen-generated title, joined at read — a nicer display label "
        "than the filename when present (None if none was generated or the document is gone; the UI "
        "falls back to document_filename).",
    )
    display_title: str | None = Field(
        default=None,
        description="The document's DISPLAY title, resolved at read exactly like the document "
        "list/grid/detail `display_title`: the value of the collection's `title_field` when one is "
        "configured and set on this document, else the parsed title. None when neither exists, the "
        "document is gone, or on the SSE stream (which re-reads only the job row). Prefer it over "
        "document_title for labelling; fall back to document_filename.",
    )
    collection_id: str = Field(description="Its collection.")
    collection_name: str | None = Field(
        default=None,
        description="The collection's name, joined at read (None if the collection is gone).",
    )
    status: str = Field(description="queued / running / done / failed / cancelled.")
    kind: str = Field(
        description="The kind of work this job tracks: 'ingest' (a full document pipeline run) or "
        "'metadata_sync' (a lightweight per-document metadata re-embed after an in-place value edit) or "
        "'rebuild_index' (a collection-level vector-store rebuild — document_id is null). "
        "Lets a client render a side-job distinctly from a full ingestion."
    )
    replay_from: str | None = Field(
        default=None,
        description="The stage an ingest job replays from on the persisted IR (no re-parse); null "
        "for a full run.",
    )
    cancel_requested: bool = Field(
        default=False,
        description="A cooperative stop has been requested; the running job stops at its next "
        "stage boundary (still 'running' until it does).",
    )
    progress: int = Field(description="0-100, completed pipeline nodes over total.")
    current_stage: str | None = Field(default=None, description="Node currently/last executed.")
    error: str | None = Field(default=None, description="Failure detail when status=failed.")
    attempt: int = Field(description="arq retry attempt (1 = first run).")
    started_at: datetime | None = Field(default=None, description="Picked up by the worker at.")
    finished_at: datetime | None = Field(default=None, description="Ended (done or failed) at.")
    updated_at: datetime = Field(description="Last progress/lifecycle write (freezes on a wedge).")
    stalled: bool = Field(
        description="A RUNNING job idle past the stall threshold — an early wedge warning."
    )
    duration_seconds: float | None = Field(
        default=None,
        description="Wall-clock run time in seconds: finished_at − started_at for a terminal job, or "
        "now − started_at for a still-running one (the elapsed time). None while the job is queued "
        "(never started). The sortable 'duration' column of the triage view.",
    )
    total_prompt_tokens: int = Field(
        description="Prompt tokens billed across this job's paid text-gen calls."
    )
    total_completion_tokens: int = Field(
        description="Completion tokens billed across this job's paid text-gen calls."
    )
    cost_usd: float = Field(
        description="USD cost of this job's paid calls (0 when nothing priceable)."
    )
    items_done: int | None = Field(
        default=None, description="Child items finished in the current fan-out stage (None off it)."
    )
    items_total: int | None = Field(
        default=None, description="The current fan-out stage's width (None when not in a fan-out)."
    )
    failed_node_id: str | None = Field(
        default=None, description="Deepest node that raised — only set on a failed job."
    )
    failed_node_kind: str | None = Field(
        default=None, description="That node's kind/family label — only set on a failed job."
    )
    failed_item_index: int | None = Field(
        default=None, description="Fan-out item index the failure sits in (None outside a fan-out)."
    )
    error_type: str | None = Field(
        default=None,
        description=(
            "Structured cause of the failure. Usually the raising exception's class name (e.g. "
            "'TimeoutError'); the reaper also attributes 'worker_killed' (the worker process was "
            "lost — crash/OOM-kill) and 'job_timeout_exceeded' (a stage wedged past the job's "
            "timeout on a live worker). Set only on a failed job."
        ),
    )


class JobPage(BaseModel):
    """
    One paginated page of jobs (a collection's, or the fleet's) — the response of ``GET /jobs``.

    The list is served bounded (the server clamps ``limit`` to its ceiling) so a heavily re-ingested
    collection — or the fleet-wide "All Jobs" view — never dumps thousands of rows at once. Iterate
    ``jobs`` for the page; read ``total`` to drive a pager.

    Attributes:
        total (int): Total jobs matching the filter (ignores paging — drives the pager).
        limit (int): The applied page size (after the server ceiling clamp).
        offset (int): The applied offset.
        jobs (list[JobStatus]): The page of jobs, in the requested order (newest first by default).
    """

    total: int = Field(
        description="Total jobs matching the filter (ignores paging — drives the pager)."
    )
    limit: int = Field(description="The applied page size (after the server ceiling clamp).")
    offset: int = Field(description="The applied offset.")
    jobs: list[JobStatus] = Field(
        description="The page of jobs, in the requested order (newest first by default)."
    )
