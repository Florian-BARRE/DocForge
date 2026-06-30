# ====== Code Summary ======
# NodeCache — node-level Merkle result cache backed by the stage_run Postgres table.
# Each completed pipeline node writes one row keyed by (document_id, node_id, fingerprint):
# a cache hit means identical inputs already produced a stored output, so a NODE_CACHED stage
# can skip re-execution. This is the cache the worker's EngineHooks.cache_load / cache_store call.
#
# Like ProviderCallCache, it takes a PostgresClient directly (no Protocol port) and manages its
# own DB sessions internally, so callers never thread an AsyncSession through the call sites.

# ====== Standard Library Imports ======
import uuid
from datetime import UTC, datetime

# ====== Third-Party Library Imports ======
from loggerplusplus import LoggerClass
from sqlalchemy import and_, select
from sqlalchemy import delete as sa_delete
from sqlalchemy.ext.asyncio import AsyncSession

# ====== Internal Project Imports ======
from common_libs.storage.postgres.client import PostgresClient
from common_libs.storage.postgres.models import StageRunModel


class NodeCache(LoggerClass):
    """
    Node-level result cache backed by the stage_run Postgres table.

    Each completed stage node writes one row: (document_id, node_id, fingerprint, output_ref).
    A cache hit means the same inputs produce the same outputs, so the node is skipped.

    State machine per row:
        running -> the node is currently executing.
        done    -> completed; ``output_ref`` points to the stored output (e.g. S3 meta key).
        failed  -> terminal failure; retried on the next pipeline run.

    The class owns its Postgres sessions (mirrors ProviderCallCache), so the engine hooks call
    get / start / put / fail without passing an AsyncSession.
    """

    def __init__(self, postgres: PostgresClient) -> None:
        """
        Initialize the NodeCache.

        Args:
            postgres (PostgresClient): Connected Postgres client used to open sessions.
        """
        LoggerClass.__init__(self)
        self._postgres = postgres

    async def _find_row(
        self,
        session: AsyncSession,
        document_id: uuid.UUID,
        node_id: str,
        fingerprint: str,
    ) -> StageRunModel | None:
        """
        Return the single stage_run row for the key, or None if absent.

        Args:
            session (AsyncSession): Active DB session.
            document_id (uuid.UUID): Document primary key.
            node_id (str): Stage identifier (e.g. ``"ingest"``, ``"parse"``).
            fingerprint (str): Node fingerprint (blake3 hex digest).

        Returns:
            StageRunModel | None: The matching row, or None on miss.
        """
        result = await session.execute(
            select(StageRunModel).where(
                and_(
                    StageRunModel.document_id == document_id,
                    StageRunModel.node_id == node_id,
                    StageRunModel.fingerprint == fingerprint,
                )
            )
        )
        return result.scalar_one_or_none()

    async def get(
        self,
        document_id: uuid.UUID,
        node_id: str,
        fingerprint: str,
    ) -> str | None:
        """
        Return the cached ``output_ref`` if the node completed successfully.

        Args:
            document_id (uuid.UUID): Document primary key.
            node_id (str): Stage identifier.
            fingerprint (str): Node fingerprint (blake3 hex digest).

        Returns:
            str | None: Stored output reference (e.g. S3 meta key), or None on a cache miss.
        """
        # 1. Look up the row for this exact (document, node, fingerprint) key
        async with self._postgres.session() as session:
            row = await self._find_row(session, document_id, node_id, fingerprint)

            # 2. Hit only when the node is 'done' and carries an output reference
            if row is not None and row.status == "done" and row.output_ref:
                self.logger.debug(
                    f"NodeCache HIT: doc={document_id} node={node_id} fp={fingerprint[:8]}..."
                )
                return row.output_ref

        self.logger.debug(
            f"NodeCache MISS: doc={document_id} node={node_id} fp={fingerprint[:8]}..."
        )
        return None

    async def start(
        self,
        document_id: uuid.UUID,
        node_id: str,
        fingerprint: str,
    ) -> None:
        """
        Record that a node started executing (status='running'), replacing any prior row.

        Args:
            document_id (uuid.UUID): Document primary key.
            node_id (str): Stage identifier.
            fingerprint (str): Node fingerprint.
        """
        async with self._postgres.session() as session:
            # 1. Remove any prior failed/pending row so we start clean
            prior = await self._find_row(session, document_id, node_id, fingerprint)
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
                    started_at=datetime.now(UTC),
                )
            )
        self.logger.debug(
            f"NodeCache START: doc={document_id} node={node_id} fp={fingerprint[:8]}..."
        )

    async def put(
        self,
        document_id: uuid.UUID,
        node_id: str,
        fingerprint: str,
        output_ref: str,
    ) -> None:
        """
        Record a successful node completion and its output reference.

        Args:
            document_id (uuid.UUID): Document primary key.
            node_id (str): Stage identifier.
            fingerprint (str): Node fingerprint.
            output_ref (str): Stored output reference (e.g. S3 meta JSON key).
        """
        async with self._postgres.session() as session:
            # 1. Look up the existing running row written by start()
            row = await self._find_row(session, document_id, node_id, fingerprint)
            if row is None:
                # 2. start() was not called (edge case) — create the row now
                row = StageRunModel(
                    document_id=document_id,
                    node_id=node_id,
                    fingerprint=fingerprint,
                )
                session.add(row)

            # 3. Mark as done with output reference and completion timestamp
            row.status = "done"
            row.output_ref = output_ref
            row.finished_at = datetime.now(UTC)
        self.logger.debug(
            f"NodeCache PUT: doc={document_id} node={node_id} "
            f"fp={fingerprint[:8]}... ref={output_ref}"
        )

    async def fail(
        self,
        document_id: uuid.UUID,
        node_id: str,
        fingerprint: str,
    ) -> None:
        """
        Mark a node as failed so it is retried on the next pipeline run.

        Args:
            document_id (uuid.UUID): Document primary key.
            node_id (str): Stage identifier.
            fingerprint (str): Node fingerprint.
        """
        async with self._postgres.session() as session:
            row = await self._find_row(session, document_id, node_id, fingerprint)
            if row is not None:
                row.status = "failed"
                row.finished_at = datetime.now(UTC)

    async def invalidate_document(
        self,
        document_id: uuid.UUID,
        node_ids: list[str] | None = None,
    ) -> int:
        """
        Drop cached stage_run rows for a document so the next run re-executes those nodes.

        Used by force-reingest: removing a node's row busts its cache hit (same inputs would
        otherwise be skipped). With ``node_ids=None`` every node is invalidated (full re-run).

        Args:
            document_id (uuid.UUID): Document whose cache entries to drop.
            node_ids (list[str] | None): Restrict to these nodes; None = all nodes.

        Returns:
            int: Number of stage_run rows removed.
        """
        async with self._postgres.session() as session:
            # 1. Build the DELETE targeting this document, optionally scoped to specific nodes
            stmt = sa_delete(StageRunModel).where(StageRunModel.document_id == document_id)
            if node_ids:
                stmt = stmt.where(StageRunModel.node_id.in_(node_ids))

            # 2. Execute and count the removed rows for the caller to log/audit
            result = await session.execute(stmt)
            removed = result.rowcount or 0

        self.logger.info(
            f"NodeCache: invalidated {removed} stage_run row(s) for document {document_id}"
        )
        return removed

    async def get_all_for_document(
        self,
        document_id: uuid.UUID,
    ) -> list[StageRunModel]:
        """
        Return all stage_run rows for a document, ordered by start time.

        Used by the /jobs/{id} endpoint to surface per-stage progress.

        Args:
            document_id (uuid.UUID): Document primary key.

        Returns:
            list[StageRunModel]: All stage run records, ordered by started_at ascending.
        """
        async with self._postgres.session() as session:
            result = await session.execute(
                select(StageRunModel)
                .where(StageRunModel.document_id == document_id)
                .order_by(StageRunModel.started_at)
            )
            return list(result.scalars().all())


__all__ = ["NodeCache"]
