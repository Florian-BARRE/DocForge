# ====== Code Summary ======
# Collection bulk re-ingest models: the request selecting documents and the accepted-jobs response.

# ====== Third-Party Library Imports ======
from pydantic import BaseModel, Field

# ====== Local Project Imports ======
from ..reingest import ReingestJobHandle


class BulkReingestRequest(BaseModel):
    """
    The re-run request over a collection's corpus (a full-pipeline re-ingest).

    Attributes:
        document_ids (list[str] | None): The explicit subset to re-run. Omit or null → EVERY document
            in the collection. An empty list is rejected by the API (an ambiguous no-op).
        force (bool): Bypass the stage cache and recompute every stage from scratch (no cache
            read/write). Use to rebuild after a code change that did not bump a node's CACHE_VERSION.
        replay_from (str | None): Replay from this post-IR stage (no re-parse); None = full re-run.
        confirm_estimate (bool): Acknowledge the estimate of a reingest above the confirm threshold.
    """

    document_ids: list[str] | None = Field(
        default=None,
        description="Explicit document UUIDs to re-run; omit for the whole collection.",
    )
    force: bool = Field(
        default=False,
        description="Bypass the stage cache and recompute every stage from scratch (no cache "
        "read/write). Use to rebuild after a code change that did not bump a node's CACHE_VERSION.",
    )
    replay_from: str | None = Field(
        default=None,
        description="Replay only this post-IR stage and its downstream from each document's PERSISTED "
        "IR (no re-parse): one of enrich, chunk, metagen_chunk, metagen_document, embed — as the "
        "collection's pipeline allows (422 lists the allowed stages). Omit for a full re-run.",
    )
    confirm_estimate: bool = Field(
        default=False,
        description="Acknowledge the cost estimate of a LARGE reingest (above the server's confirm "
        "threshold). Without it such a call is refused 409 estimate_required carrying the estimate "
        "summary; review it and resend with true.",
    )


class BulkReingestAccepted(BaseModel):
    """
    The accepted bulk re-run — the runs execute asynchronously (poll each job).

    A match count above the server's per-call fan-out ceiling enqueues only the first N and reports
    ``capped=true`` with the full ``matched`` count, so one call never floods the queue.

    Attributes:
        collection_id (str): The target collection.
        count (int): Jobs enqueued (= ``enqueued``; kept for backward compatibility).
        matched (int): Documents the request resolved to (before the cap).
        enqueued (int): Jobs actually enqueued (<= the fan-out ceiling).
        capped (bool): True when ``matched`` exceeded the per-call fan-out ceiling.
        max_fanout (int): The per-call fan-out ceiling that was applied.
        skipped_in_flight (int): Documents skipped because a run was already active for them.
        jobs (list[ReingestJobHandle]): One handle per enqueued run.
    """

    collection_id: str = Field(description="The target collection's UUID.")
    count: int = Field(description="Jobs enqueued (= enqueued; kept for backward compatibility).")
    matched: int = Field(description="Documents the request resolved to (before the cap).")
    enqueued: int = Field(description="Jobs actually enqueued (<= the fan-out ceiling).")
    capped: bool = Field(
        description="True when the match count exceeded the per-call fan-out ceiling."
    )
    max_fanout: int = Field(description="The per-call fan-out ceiling that was applied.")
    skipped_in_flight: int = Field(
        default=0,
        description="Documents skipped because an ingestion job was already active for them.",
    )
    skipped_not_replayable: int = Field(
        default=0,
        description="Documents skipped by a replay_from run because they have no persisted IR.",
    )
    jobs: list[ReingestJobHandle] = Field(description="One handle per enqueued run.")
