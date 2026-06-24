# ====== Code Summary ======
# ResourceAdmitter (Brique D) — runtime back-pressure gate that answers "can the system accept
# MORE load right now?", a sibling of the config-time AdmissionValidator ("is THIS document
# admissible?"). It reads cheap live signals (arq ZCARD + indexed Postgres COUNT/SUM) and returns
# an AdmissionDecision: 429 on capacity, 409 on cumulative budget. The decision logic (evaluate) is
# pure; only admit() does I/O, and it is fail-soft — any introspection error admits, so a telemetry
# failure can never block ingestion.

# ====== Standard Library Imports ======
from __future__ import annotations

from typing import TYPE_CHECKING

# ====== Third-Party Library Imports ======
from loggerplusplus import LoggerClass

# ====== Local Project Imports ======
from .models import AdmissionDecision, AdmissionSnapshot, ResourceLimits

if TYPE_CHECKING:
    from backend.libs.observability.queue import QueueIntrospector
    from common_libs.storage.postgres.models import CollectionModel
    from common_libs.storage.postgres.repositories import JobRepository
    from sqlalchemy.ext.asyncio import AsyncSession


class ResourceAdmitter(LoggerClass):
    """
    Regulates pipeline enqueue based on live queue depth, in-flight count, and cumulative budget.

    Global thresholds are injected from RUNTIME_CONFIG (0 = unlimited); per-collection thresholds
    are read from the collection row at decision time. The gate is best-effort protection, not a
    correctness invariant: if its own introspection fails it admits and logs a warning.
    """

    def __init__(self, *, enabled: bool, max_queue_depth: int, max_in_flight_global: int) -> None:
        """
        Initialize the admitter with the deployment-global limits.

        Args:
            enabled (bool): Master switch — when False every request is admitted.
            max_queue_depth (int): Reject when arq backlog reaches this (0 = unlimited).
            max_in_flight_global (int): Reject when running jobs reach this (0 = unlimited).
        """
        LoggerClass.__init__(self)
        self._enabled = enabled
        self._max_queue_depth = max_queue_depth
        self._max_in_flight_global = max_in_flight_global
        self.logger.info(
            f"ResourceAdmitter enabled={enabled} max_queue_depth={max_queue_depth} "
            f"max_in_flight_global={max_in_flight_global}"
        )

    async def __gather(
        self,
        session: "AsyncSession",
        collection: "CollectionModel",
        queue_introspector: "QueueIntrospector",
        job_repo: "JobRepository",
    ) -> AdmissionSnapshot:
        """
        Collect the live load numbers for the decision (all cheap: ZCARD + indexed COUNT/SUM).

        Args:
            session (AsyncSession): Active session for the Postgres reads.
            collection (CollectionModel): Target collection (scopes the per-collection numbers).
            queue_introspector (QueueIntrospector): Read-only arq queue view (backlog depth).
            job_repo (JobRepository): Job counts + cumulative spend source.

        Returns:
            AdmissionSnapshot: The four signals evaluate() reasons over.
        """
        # 1. Backlog depth (Redis ZCARD, O(1)) and global running count (indexed Postgres)
        queue_depth = await queue_introspector.queue_depth()
        global_counts = await job_repo.count_by_status(session)

        # 2. Per-collection in-flight (running + pending) and cumulative spend
        coll_counts = await job_repo.count_by_status(session, collection_id=collection.id)
        spent = await job_repo.sum_budget_by_collection(session, collection.id)

        return AdmissionSnapshot(
            queue_depth=queue_depth,
            running_global=global_counts.get("running", 0),
            inflight_collection=coll_counts.get("running", 0) + coll_counts.get("pending", 0),
            collection_spent=spent,
        )

    def evaluate(self, snapshot: AdmissionSnapshot, limits: ResourceLimits) -> AdmissionDecision:
        """
        Decide admission from a snapshot + limits — pure function, no I/O.

        Order: budget (409) before capacity (429), then global → backlog → per-collection. The two
        global ints use 0 as an "unlimited" sentinel; the per-collection fields use None.

        Args:
            snapshot (AdmissionSnapshot): Live load numbers.
            limits (ResourceLimits): Resolved global + per-collection thresholds.

        Returns:
            AdmissionDecision: Admit, or reject with the appropriate HTTP status + detail.
        """
        # 0. Master switch off → never throttle
        if not self._enabled:
            return AdmissionDecision.admit("admission disabled")

        # 1. Budget pre-flight — a job's cost is unknown before it runs, so we can only reject on
        #    cumulative collection spend already at/over the cap (the per-job S2 hard-stop stays).
        if limits.budget_cap_usd is not None and snapshot.collection_spent >= limits.budget_cap_usd:
            return AdmissionDecision.reject(
                status_code=409,
                reason="collection budget exhausted",
                detail={
                    "error": "Collection budget exhausted.",
                    "budget_cap_usd": limits.budget_cap_usd,
                    "budget_spent_usd": round(snapshot.collection_spent, 6),
                },
            )

        # 2. Global in-flight cap (running jobs across all collections)
        if 0 < limits.max_in_flight_global <= snapshot.running_global:
            return AdmissionDecision.reject(
                status_code=429,
                reason="global in-flight limit reached",
                detail={
                    "error": "System at capacity (global in-flight limit reached).",
                    "limit": limits.max_in_flight_global,
                    "running": snapshot.running_global,
                },
            )

        # 3. Backlog cap (pending jobs queued in arq)
        if 0 < limits.max_queue_depth <= snapshot.queue_depth:
            return AdmissionDecision.reject(
                status_code=429,
                reason="queue backlog limit reached",
                detail={
                    "error": "System at capacity (queue backlog limit reached).",
                    "limit": limits.max_queue_depth,
                    "queue_depth": snapshot.queue_depth,
                },
            )

        # 4. Per-collection in-flight cap (running + pending scoped to this collection)
        if (
            limits.max_in_flight_collection is not None
            and snapshot.inflight_collection >= limits.max_in_flight_collection
        ):
            return AdmissionDecision.reject(
                status_code=429,
                reason="collection in-flight limit reached",
                detail={
                    "error": "Collection at capacity (in-flight limit reached).",
                    "limit": limits.max_in_flight_collection,
                    "in_flight": snapshot.inflight_collection,
                },
            )

        # 5. Under every applicable limit → admit
        return AdmissionDecision.admit("within limits")

    async def admit(
        self,
        *,
        session: "AsyncSession",
        collection: "CollectionModel",
        queue_introspector: "QueueIntrospector",
        job_repo: "JobRepository",
    ) -> AdmissionDecision:
        """
        Gather the live snapshot and evaluate it — the entry point the ingest router calls.

        FAIL-SOFT: any error while gathering the snapshot is caught and turned into an ADMIT (with a
        warning), because back-pressure is best-effort and must never block ingestion on a telemetry
        outage (Redis/Postgres read failure).

        Args:
            session (AsyncSession): Active session for the Postgres reads.
            collection (CollectionModel): Target collection (carries per-collection limits).
            queue_introspector (QueueIntrospector): Read-only arq queue view.
            job_repo (JobRepository): Job counts + cumulative spend source.

        Returns:
            AdmissionDecision: The admission outcome.
        """
        # 1. Fast path — gate disabled, no I/O at all
        if not self._enabled:
            return AdmissionDecision.admit("admission disabled")

        # 2. Gather live signals, fail-soft on any introspection error
        try:
            snapshot = await self.__gather(session, collection, queue_introspector, job_repo)
        except Exception as exc:
            self.logger.warning(
                f"Resource admission introspection failed ({exc}); admitting fail-soft."
            )
            return AdmissionDecision.admit("introspection failed (fail-soft)")

        # 3. Resolve the effective limits (globals + this collection's caps) and decide
        limits = ResourceLimits(
            max_queue_depth=self._max_queue_depth,
            max_in_flight_global=self._max_in_flight_global,
            max_in_flight_collection=collection.max_in_flight,
            budget_cap_usd=collection.budget_cap_usd,
        )
        decision = self.evaluate(snapshot, limits)
        if not decision.admitted:
            self.logger.info(
                f"Resource admission rejected collection={collection.id} "
                f"status={decision.status_code} reason={decision.reason!r}"
            )
        return decision


# ------------------- Public API ------------------- #
__all__ = ["ResourceAdmitter"]
