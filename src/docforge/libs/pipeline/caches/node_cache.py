# ====== Code Summary ======
# NodeCache — node-level result cache facade for the P2 stage engine.
# Wraps the stage_run Postgres table: each row records one pipeline node execution.
# Cache hit condition: (document_id, node_id, fingerprint) with status='done'.
# All SQL operations live in NodeCacheOps (node_cache_ops.py); this class is the typed,
# instance-bound facade that the engine injects and calls.

# ====== Standard Library Imports ======
from __future__ import annotations

import uuid

# ====== Third-Party Library Imports ======
from loggerplusplus import LoggerClass
from sqlalchemy.ext.asyncio import AsyncSession

# ====== Internal Project Imports ======
from libs.storage.postgres.models import StageRunModel

# ====== Local Project Imports ======
from .node_cache_ops import NodeCacheOps


class NodeCache(LoggerClass):
    """
    Node-level result cache backed by the stage_run Postgres table.

    Each completed stage node writes one row: (document_id, node_id, fingerprint, output_ref).
    A cache hit means the same inputs produce the same outputs — skip re-execution.

    State machine per row:
        running → the node is currently executing.
        done    → completed; ``output_ref`` points to the S3 meta JSON key.
        failed  → terminal failure; will be retried on next pipeline run.

    All operations are delegated to NodeCacheOps; this facade keeps the public contract.
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
        return await NodeCacheOps.get(session, document_id, node_id, fingerprint)

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
        await NodeCacheOps.start(session, document_id, node_id, fingerprint)

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
        await NodeCacheOps.put(session, document_id, node_id, fingerprint, output_ref)

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
        await NodeCacheOps.fail(session, document_id, node_id, fingerprint)

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
        return await NodeCacheOps.invalidate_document(session, document_id, node_ids)

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
        return await NodeCacheOps.get_all_for_document(session, document_id)
