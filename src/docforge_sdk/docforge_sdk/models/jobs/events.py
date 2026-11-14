# ====== Code Summary ======
# Job trace models: one node of the execution trace, its heavy payload, and the full trace.

# ====== Standard Library Imports ======
from datetime import datetime
from typing import Any

# ====== Third-Party Library Imports ======
from pydantic import BaseModel, Field


class JobEvent(BaseModel):
    """
    One node of the job's execution trace — written by the worker.

    The trace is the FULL per-node execution tree: root stages carry live status/timing/usage, and
    every nested node (group children, per-item ForEach body instances) is persisted after the run.
    The list stays FLAT — the UI rebuilds the tree from ``node_path`` + ``depth`` + ``parent_path``.

    Attributes:
        stage (str): The pipeline node id (the node's own id segment).
        status (str): success / failed / skipped.
        node_kind (str | None): The stage's structural kind (action/group/foreach) or the node's
            concrete kind — None for rows written before this column landed.
        started_at (datetime | None): Node start.
        finished_at (datetime | None): Node end.
        detail (str | None): Duration, or the error when failed.
        prompt_tokens (int | None): Prompt tokens billed by this stage; null when none.
        completion_tokens (int | None): Completion tokens billed; null when none.
        cost_usd (float | None): USD cost; null when no usage or unknown price.
        score (float | None): Quality score in [0, 1] of a scored-family node; null otherwise.
        node_path (str | None): Materialized tree path (root = bare id, nested = dotted); null legacy.
        depth (int | None): Tree depth (0 = root stage); null for legacy rows.
        parent_path (str | None): Parent node's node_path; null for roots and legacy rows.
        item_index (int | None): ForEach item index when inside a fan-out; null otherwise.
    """

    stage: str = Field(description="The pipeline node id (the node's own id segment).")
    status: str = Field(description="success / failed / skipped.")
    node_kind: str | None = Field(
        default=None,
        description="The stage's structural kind (action/group/foreach) or the node's concrete "
        "kind — None for rows written before this column landed.",
    )
    started_at: datetime | None = Field(default=None, description="Node start.")
    finished_at: datetime | None = Field(default=None, description="Node end.")
    detail: str | None = Field(default=None, description="Duration, or the error when failed.")
    prompt_tokens: int | None = Field(
        default=None, description="Prompt tokens billed by this stage; null when it made none."
    )
    completion_tokens: int | None = Field(
        default=None, description="Completion tokens billed by this stage; null when none."
    )
    cost_usd: float | None = Field(
        default=None, description="USD cost of this stage; null when no usage or unknown price."
    )
    score: float | None = Field(
        default=None,
        description="Quality score in [0, 1] of a scored-family node (parser/ocr/…), what a "
        "ScoreBelow edge compares to its threshold. None for non-scored nodes and legacy rows.",
    )
    node_path: str | None = Field(
        default=None,
        description="Materialized path of this node in the execution tree — root = bare node id, "
        "nested = dotted path (e.g. 'enrich.figures[3].vlm'). None for legacy rows (pre-tree).",
    )
    depth: int | None = Field(
        default=None,
        description="Depth in the execution tree: 0 = root stage, larger = more nested. None for "
        "legacy rows (the UI treats it as 0).",
    )
    parent_path: str | None = Field(
        default=None,
        description="node_path of this node's parent — None for root stages and legacy rows.",
    )
    item_index: int | None = Field(
        default=None,
        description="Zero-based ForEach item index when this node runs inside a fan-out; None "
        "outside any fan-out (and for legacy rows).",
    )
    event_id: str = Field(
        description="The stage-event row's UUID — the stable handle the full-payload fetch route "
        "addresses (GET /jobs/{job_id}/events/{event_id}/payload)."
    )
    input_summary: dict[str, Any] | None = Field(
        default=None,
        description="Bounded SHAPE descriptor of the node's resolved input (type/fields/sizes/hash) "
        "— never the raw content. None when trace capture was off, the node had no input, or for "
        "legacy rows.",
    )
    output_summary: dict[str, Any] | None = Field(
        default=None,
        description="Bounded SHAPE descriptor of the node's output — never the raw content. None "
        "when trace capture was off, the node produced nothing, or for legacy rows.",
    )
    has_full_input: bool | None = Field(
        default=None,
        description="Whether a FULL raw input payload was stored in the object store (the opt-in "
        "full tier) and can be fetched via the payload route. None/false both mean unavailable.",
    )
    has_full_output: bool | None = Field(
        default=None,
        description="Whether a FULL raw output payload was stored and can be fetched via the payload "
        "route. None/false both mean unavailable.",
    )


class JobEventPayload(BaseModel):
    """
    One stage-event's FULL raw input or output payload, fetched on demand from the object store.

    The trace list (``JobEvent``) carries only the cheap shape summaries; the FULL raw payload of a
    node (stored only when the collection opted into ``trace_verbosity='full'``) is served one slot at
    a time by ``GET /jobs/{job_id}/events/{event_id}/payload?slot=input|output``. The stored payload is
    the node's resolved JSON, so ``payload`` is an arbitrary JSON value.

    Attributes:
        job_id (str): The job the traced node belongs to.
        event_id (str): The stage-event row's UUID the payload was read from.
        slot (str): Which side was fetched: 'input' or 'output'.
        stage (str): The node's stage id (its own id segment) — a display label.
        node_path (str | None): The node's materialized tree path (None for legacy rows).
        truncated (bool): True when the stored object exceeds the read cap: ``payload`` is then None
            and only ``size_bytes`` describes it.
        size_bytes (int): The stored payload object's size in bytes.
        payload (Any): The node's full raw payload (arbitrary JSON), or None when truncated.
    """

    job_id: str = Field(description="The job the traced node belongs to.")
    event_id: str = Field(description="The stage-event row's UUID the payload was read from.")
    slot: str = Field(description="Which side was fetched: 'input' or 'output'.")
    stage: str = Field(description="The node's stage id (its own id segment) — a display label.")
    node_path: str | None = Field(
        default=None,
        description="The node's materialized tree path (None for legacy rows without one).",
    )
    truncated: bool = Field(
        description="True when the stored object exceeds the read cap (or was stored past the "
        "capture cap): ``payload`` is then None and only ``size_bytes`` describes it."
    )
    size_bytes: int = Field(description="The stored payload object's size in bytes.")
    payload: Any = Field(
        default=None,
        description="The node's full raw payload (arbitrary JSON), or None when truncated past the "
        "read cap.",
    )


class JobTrace(BaseModel):
    """
    A job's full per-node execution tree, flat — the UI rebuilds the tree from node_path/depth.

    Attributes:
        job_id (str): The traced job.
        events (list[JobEvent]): Every node of the run, flat and pre-order.
    """

    job_id: str = Field(description="The traced job.")
    events: list[JobEvent] = Field(
        default_factory=list,
        description="Every node of the run, flat and pre-order (parent before children, ForEach "
        "items by index) — the UI nests them via node_path/depth.",
    )
