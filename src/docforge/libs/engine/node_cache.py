# ====== Code Summary ======
# NodeCache — node-level result cache for the P2 stage engine.
# Wraps the stage_run Postgres table: each row records one pipeline node execution.
# Cache hit condition: (document_id, node_id, fingerprint) with status='done'.

# ====== Standard Library Imports ======
from __future__ import annotations

import uuid
from datetime import datetime, timezone

# ====== Third-Party Library Imports ======
from loggerplusplus import LoggerClass
from sqlalchemy import and_, select
from sqlalchemy import delete as sa_delete
from sqlalchemy.ext.asyncio import AsyncSession

# ====== Internal Project Imports ======
from libs.data.storage.postgres.models import StageRunModel


class NodeCache(LoggerClass):
    """
    Node-level result cache backed by the stage_run Postgres table.

    Each completed stage node writes one row: (document_id, node_id, fingerprint, output_ref).
    A cache hit means the same inputs produce the same outputs — skip re-execution.

    State machine per row:
        running → the node is currently executing.
        done    → completed; ``output_ref`` points to the S3 meta JSON key.
        failed  → terminal failure; will be retried on next pipeline run.
    """

    def __init__(self) -> None:
        """Initialize the NodeCache logger."""
        LoggerClass.__init__(self)

    async def get(
        self,
        session: AsyncSession,
        document_id: uuid.UUID,
        node_id: str,
        fingerprint: str,
    ) -> str | None:
        """
        Return the cached ``output_ref`` if the node completed successfully.

        Args:
            session (AsyncSession): Active DB session.
            document_id (uuid.UUID): Document primary key.
            node_id (str): Stage identifier (e.g. ``"s0"``, ``"s1"``).
            fingerprint (str): Node fingerprint (blake3 hex digest).

        Returns:
            str | None: S3 key of the output meta JSON, or None on cache miss.
        """
        result = await session.execute(
            select(StageRunModel).where(
                and_(
                    StageRunModel.document_id == document_id,
                    StageRunModel.node_id == node_id,
                    StageRunModel.fingerprint == fingerprint,
                    StageRunModel.status == "done",
                )
            )
        )
        row = result.scalar_one_or_none()
        if row is not None and row.output_ref:
            self.logger.debug(
                f"NodeCache HIT: doc={document_id} node={node_id} fp={fingerprint[:8]}…"
            )
            return row.output_ref

        self.logger.debug(
            f"NodeCache MISS: doc={document_id} node={node_id} fp={fingerprint[:8]}…"
        )
        return None

    async def start(
        self,
        session: AsyncSession,
        document_id: uuid.UUID,
        node_id: str,
        fingerprint: str,
    ) -> None:
        """
        Record that a node has started executing (status='running').

        Replaces any prior failed/pending row for the same (document_id, node_id, fingerprint).

        Args:
            session (AsyncSession): Active DB session.
            document_id (uuid.UUID): Document primary key.
            node_id (str): Stage identifier.
            fingerprint (str): Node fingerprint.
        """
        # 1. Remove any prior failed/pending row so we start clean
        existing = await session.execute(
            select(StageRunModel).where(
                and_(
                    StageRunModel.document_id == document_id,
                    StageRunModel.node_id == node_id,
                    StageRunModel.fingerprint == fingerprint,
                )
            )
        )
        prior = existing.scalar_one_or_none()
        if prior is not None:
            await session.delete(prior)
            await session.flush()

        # 2. Insert a fresh running record
        session.add(
            StageRunModel(
                document_id=document_id,
                node_id=node_id,
                fingerprint=fingerprint,
                status="running",
                started_at=datetime.now(timezone.utc),
            )
        )
        await session.flush()
        self.logger.debug(
            f"NodeCache START: doc={document_id} node={node_id} fp={fingerprint[:8]}…"
        )

    async def put(
        self,
        session: AsyncSession,
        document_id: uuid.UUID,
        node_id: str,
        fingerprint: str,
        output_ref: str,
    ) -> None:
        """
        Record a successful node completion and its output reference.

        Args:
            session (AsyncSession): Active DB session.
            document_id (uuid.UUID): Document primary key.
            node_id (str): Stage identifier.
            fingerprint (str): Node fingerprint.
            output_ref (str): S3 key of the output meta JSON.
        """
        # 1. Look up the existing running row written by start()
        result = await session.execute(
            select(StageRunModel).where(
                and_(
                    StageRunModel.document_id == document_id,
                    StageRunModel.node_id == node_id,
                    StageRunModel.fingerprint == fingerprint,
                )
            )
        )
        row = result.scalar_one_or_none()
        if row is None:
            # 2. start() was not called (edge case) — create the row now
            row = StageRunModel(
                document_id=document_id,
                node_id=node_id,
                fingerprint=fingerprint,
            )
            session.add(row)

        # 3. Mark as done with output reference and timestamp
        row.status = "done"
        row.output_ref = output_ref
        row.finished_at = datetime.now(timezone.utc)
        await session.flush()

        self.logger.debug(
            f"NodeCache PUT: doc={document_id} node={node_id} "
            f"fp={fingerprint[:8]}… ref={output_ref}"
        )

    async def fail(
        self,
        session: AsyncSession,
        document_id: uuid.UUID,
        node_id: str,
        fingerprint: str,
    ) -> None:
        """
        Mark a node as failed so it is retried on the next pipeline run.

        Args:
            session (AsyncSession): Active DB session.
            document_id (uuid.UUID): Document primary key.
            node_id (str): Stage identifier.
            fingerprint (str): Node fingerprint.
        """
        # 1. Locate the running row to update its terminal state
        result = await session.execute(
            select(StageRunModel).where(
                and_(
                    StageRunModel.document_id == document_id,
                    StageRunModel.node_id == node_id,
                    StageRunModel.fingerprint == fingerprint,
                )
            )
        )
        row = result.scalar_one_or_none()
        # 2. Mark the row as failed so the next run re-executes this node
        if row is not None:
            row.status = "failed"
            row.finished_at = datetime.now(timezone.utc)
            await session.flush()

    async def invalidate_document(
        self,
        session: AsyncSession,
        document_id: uuid.UUID,
        node_ids: list[str] | None = None,
    ) -> int:
        """
        Drop cached stage_run rows for a document so the next run re-executes those nodes.

        Used by force-reingest: removing a node's row busts its cache hit (same inputs would
        otherwise be skipped). With ``node_ids=None`` every node is invalidated (full re-run).

        Args:
            session (AsyncSession): Active session.
            document_id (uuid.UUID): Document whose cache entries to drop.
            node_ids (list[str] | None): Restrict to these nodes; None = all nodes.

        Returns:
            int: Number of stage_run rows removed.
        """
        # 1. Build the DELETE targeting this document, optionally scoped to specific nodes
        stmt = sa_delete(StageRunModel).where(StageRunModel.document_id == document_id)
        if node_ids:
            stmt = stmt.where(StageRunModel.node_id.in_(node_ids))
        # 2. Execute and count the removed rows for the caller to log/audit
        result = await session.execute(stmt)
        removed = result.rowcount or 0
        self.logger.info(f"NodeCache: invalidated {removed} stage_run row(s) for document {document_id}")
        return removed

    async def get_all_for_document(
        self,
        session: AsyncSession,
        document_id: uuid.UUID,
    ) -> list[StageRunModel]:
        """
        Return all stage_run rows for a document, ordered by start time.

        Used by the /jobs/{id} endpoint to surface per-stage progress.

        Args:
            session (AsyncSession): Active DB session.
            document_id (uuid.UUID): Document primary key.

        Returns:
            list[StageRunModel]: All stage run records, ordered by started_at ascending.
        """
        result = await session.execute(
            select(StageRunModel)
            .where(StageRunModel.document_id == document_id)
            .order_by(StageRunModel.started_at)
        )
        return list(result.scalars().all())
