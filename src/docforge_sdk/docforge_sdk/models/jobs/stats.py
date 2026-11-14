# ====== Code Summary ======
# Job statistics models: backlog counters, per-stage durations, cost roll-up, failure
# breakdowns, the time series and the new-failures feed.

# ====== Standard Library Imports ======
from datetime import datetime

# ====== Third-Party Library Imports ======
from pydantic import BaseModel, Field


class QueueDepth(BaseModel):
    """Backlog counters — pending (queued, unclaimed) and running jobs, fleet-wide or per-collection."""

    pending: int = Field(description="Jobs queued but not yet claimed by a worker.")
    running: int = Field(description="Jobs a worker is currently executing.")


class StageDurations(BaseModel):
    """Average per-stage wall-clock for a collection — the basis for a running job's ETA."""

    collection_id: str = Field(description="The collection the averages were computed over.")
    stage_seconds: dict[str, float] = Field(
        default_factory=dict, description="Stage id → average wall-clock seconds over DONE jobs."
    )


class CollectionCost(BaseModel):
    """The collection's paid text-gen roll-up — tokens and USD summed over its documents' jobs."""

    collection_id: str = Field(description="The collection totalled.")
    total_prompt_tokens: int = Field(description="Sum of input tokens over the collection's jobs.")
    total_completion_tokens: int = Field(description="Sum of output tokens over the jobs.")
    cost_usd: float = Field(description="Sum of USD cost over the jobs.")
    document_count: int = Field(description="Number of jobs (documents) in the roll-up.")


class FailureBucket(BaseModel):
    """
    One failure-breakdown bucket — a cause/stage label and how many failed jobs carry it.

    Attributes:
        label (str): The bucket value — an error class, a stage/node id, or 'unknown' (null column).
        count (int): Number of failed jobs in this bucket over the window.
    """

    label: str = Field(
        description="The bucket's value — an error class (by_error_type), a stage/node id (by_stage), "
        "or the literal 'unknown' when the underlying column was null (unattributed failure)."
    )
    count: int = Field(description="Number of failed jobs in this bucket over the window.")


class CollectionFailureBucket(BaseModel):
    """
    One failure-breakdown bucket grouped by collection — id, name and failure count.

    Attributes:
        collection_id (str): The collection the failures belong to.
        collection_name (str | None): The collection's name (None when the collection row is gone).
        count (int): Number of failed jobs in this collection over the window.
    """

    collection_id: str = Field(description="The collection the failures belong to.")
    collection_name: str | None = Field(
        default=None, description="The collection's name (None when the collection row is gone)."
    )
    count: int = Field(description="Number of failed jobs in this collection over the window.")


class FailureBreakdown(BaseModel):
    """
    Failure aggregation over a time window — the "why is it breaking" panel.

    Three roll-ups of the window's FAILED jobs, each ordered by descending count and bounded to the
    dominant causes: by structured error class, by the stage/node the job died in, and by collection.

    Attributes:
        collection_id (str | None): The collection scoped to, or None for a fleet-wide breakdown.
        window_hours (int): The window width in hours the breakdown was computed over.
        since (datetime): The window start instant (now − window_hours).
        total_failed (int): Total failed jobs in the window (the panel headline).
        by_error_type (list[FailureBucket]): Top failure causes by error class, biggest first.
        by_stage (list[FailureBucket]): Top failures by the stage the job died in, biggest first.
        by_collection (list[CollectionFailureBucket]): Top failures by collection, biggest first.
    """

    collection_id: str | None = Field(
        default=None, description="The collection scoped to, or None for a fleet-wide breakdown."
    )
    window_hours: int = Field(
        description="The window width in hours the breakdown was computed over."
    )
    since: datetime = Field(description="The window start instant (now − window_hours).")
    total_failed: int = Field(description="Total failed jobs in the window (the panel headline).")
    by_error_type: list[FailureBucket] = Field(
        default_factory=list,
        description="Top failure causes by structured error class, biggest first.",
    )
    by_stage: list[FailureBucket] = Field(
        default_factory=list,
        description="Top failures by the stage/node the job died in (current_stage), biggest first.",
    )
    by_collection: list[CollectionFailureBucket] = Field(
        default_factory=list,
        description="Top failures by collection, biggest first (present on a fleet-wide breakdown).",
    )


class TimeseriesBucket(BaseModel):
    """
    One hourly bucket of the job trends — arrivals, completions and reconstructed backlog.

    Attributes:
        bucket_start (datetime): The bucket's start instant (a UTC hour boundary).
        created (int): Jobs created (arrived) during this hour.
        done (int): Jobs that completed successfully during this hour.
        failed (int): Jobs that failed during this hour.
        backlog (int): Instantaneous backlog (queued + running) at the END of this hour.
    """

    bucket_start: datetime = Field(description="The bucket's start instant (a UTC hour boundary).")
    created: int = Field(description="Jobs created (arrived) during this hour.")
    done: int = Field(description="Jobs that completed successfully during this hour.")
    failed: int = Field(description="Jobs that failed during this hour.")
    backlog: int = Field(
        description="Instantaneous backlog (queued + running) at the END of this hour, reconstructed "
        "from the cumulative arrivals/completions plus the pre-window baseline."
    )


class JobTimeseries(BaseModel):
    """
    Lightweight job trends — contiguous hourly buckets computed from the job table (no Prometheus).

    Attributes:
        collection_id (str | None): The collection scoped to, or None for a fleet-wide series.
        window_hours (int): The window width in hours the series spans.
        bucket_seconds (int): Bucket width in seconds (3600 — hourly).
        buckets (list[TimeseriesBucket]): Contiguous hourly buckets, oldest first.
    """

    collection_id: str | None = Field(
        default=None, description="The collection scoped to, or None for a fleet-wide series."
    )
    window_hours: int = Field(description="The window width in hours the series spans.")
    bucket_seconds: int = Field(description="Bucket width in seconds (3600 — hourly).")
    buckets: list[TimeseriesBucket] = Field(
        default_factory=list,
        description="Contiguous hourly buckets, oldest first, one per hour across the window.",
    )


class NewFailures(BaseModel):
    """
    The "X new failures since you last looked" signal — a count (and optional ids) past a cursor.

    Attributes:
        since (datetime): The last-seen cursor the count was computed against.
        count (int): Jobs that failed strictly after the cursor.
        job_ids (list[str]): Ids of the new failures, newest first (bounded); empty unless asked.
        latest_failed_at (datetime | None): The newest failure's finish time (the next cursor).
    """

    since: datetime = Field(description="The last-seen cursor the count was computed against.")
    count: int = Field(description="Jobs that failed strictly after the cursor.")
    job_ids: list[str] = Field(
        default_factory=list,
        description="Ids of the new failures, newest first (bounded); empty unless the caller asked "
        "for them (include_ids) or there are none.",
    )
    latest_failed_at: datetime | None = Field(
        default=None,
        description="The newest failure's finish time — the value to pass as the next 'since' cursor "
        "(None when there are no new failures).",
    )
