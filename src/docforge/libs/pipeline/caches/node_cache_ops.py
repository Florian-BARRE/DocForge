# ====== Code Summary ======
# NodeCacheOps — static SQL operations behind the NodeCache facade.  Owns the shared
# (document_id, node_id, fingerprint) row lookup plus the mutation operations
# (start / put / fail / invalidate_document) and the per-document listing.  Extracted from
# NodeCache so the public facade stays a thin, single-responsibility cache interface.

# ====== Standard Library Imports ======
from __future__ import annotations

import uuid
from datetime import UTC, datetime

# ====== Third-Party Library Imports ======
from loggerplusplus import loggerplusplus
from sqlalchemy import and_, select
from sqlalchemy import delete as sa_delete
from sqlalchemy.ext.asyncio import AsyncSession

# ====== Internal Project Imports ======
from libs.data.storage.postgres.models import StageRunModel


class NodeCacheOps:
    """
    Static SQL operations for the stage_run node cache.

    Every operation is keyed by ``(document_id, node_id, fingerprint)``.  These helpers
    encapsulate the SQLAlchemy statements so :class:`NodeCache` reads as a thin facade.
    """

    logger = loggerplusplus.bind(identifier="NodeCache")

    def __new__(cls, *args: object, **kwargs: object) -> None:  # type: ignore[misc]
        """Block instantiation — this is a static-only helper class."""
        raise TypeError("NodeCacheOps is a static-only class and cannot be instantiated.")

    @classmethod
    async def _find_row(
        cls,
        session: AsyncSession,
        document_id: uuid.UUID,
        node_id: str,
        fingerprint: str,
    ) -> StageRunModel | None:
        """Return the single stage_run row for the key, or None if absent."""
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

    @classmethod
    async def get(
        cls,
        session: AsyncSession,
        document_id: uuid.UUID,
        node_id: str,
        fingerprint: str,
    ) -> str | None:
        """Return the cached ``output_ref`` if the node completed successfully, else None."""
        row = await cls._find_row(session, document_id, node_id, fingerprint)
        if row is not None and row.status == "done" and row.output_ref:
            cls.logger.debug(
                f"NodeCache HIT: doc={document_id} node={node_id} fp={fingerprint[:8]}…"
            )
            return row.output_ref
        cls.logger.debug(
            f"NodeCache MISS: doc={document_id} node={node_id} fp={fingerprint[:8]}…"
        )
        return None

    @classmethod
    async def start(
        cls,
        session: AsyncSession,
        document_id: uuid.UUID,
        node_id: str,
        fingerprint: str,
    ) -> None:
        """Record that a node started executing, replacing any prior row for the key."""
        # 1. Remove any prior failed/pending row so we start clean
        prior = await cls._find_row(session, document_id, node_id, fingerprint)
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
        await session.flush()
        cls.logger.debug(
            f"NodeCache START: doc={document_id} node={node_id} fp={fingerprint[:8]}…"
        )

    @classmethod
    async def put(
        cls,
        session: AsyncSession,
        document_id: uuid.UUID,
        node_id: str,
        fingerprint: str,
        output_ref: str,
    ) -> None:
        """Record a successful node completion and its output reference."""
        # 1. Look up the existing running row written by start()
        row = await cls._find_row(session, document_id, node_id, fingerprint)
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
        row.finished_at = datetime.now(UTC)
        await session.flush()
        cls.logger.debug(
            f"NodeCache PUT: doc={document_id} node={node_id} "
            f"fp={fingerprint[:8]}… ref={output_ref}"
        )

    @classmethod
    async def fail(
        cls,
        session: AsyncSession,
        document_id: uuid.UUID,
        node_id: str,
        fingerprint: str,
    ) -> None:
        """Mark a node as failed so it is retried on the next pipeline run."""
        row = await cls._find_row(session, document_id, node_id, fingerprint)
        if row is not None:
            row.status = "failed"
            row.finished_at = datetime.now(UTC)
            await session.flush()

    @classmethod
    async def invalidate_document(
        cls,
        session: AsyncSession,
        document_id: uuid.UUID,
        node_ids: list[str] | None = None,
    ) -> int:
        """Drop cached stage_run rows for a document; return the number removed."""
        # 1. Build the DELETE targeting this document, optionally scoped to specific nodes
        stmt = sa_delete(StageRunModel).where(StageRunModel.document_id == document_id)
        if node_ids:
            stmt = stmt.where(StageRunModel.node_id.in_(node_ids))
        # 2. Execute and count the removed rows for the caller to log/audit
        result = await session.execute(stmt)
        removed = result.rowcount or 0
        cls.logger.info(
            f"NodeCache: invalidated {removed} stage_run row(s) for document {document_id}"
        )
        return removed

    @classmethod
    async def get_all_for_document(
        cls,
        session: AsyncSession,
        document_id: uuid.UUID,
    ) -> list[StageRunModel]:
        """Return all stage_run rows for a document, ordered by start time."""
        result = await session.execute(
            select(StageRunModel)
            .where(StageRunModel.document_id == document_id)
            .order_by(StageRunModel.started_at)
        )
        return list(result.scalars().all())


# ------------------- Public API ------------------- #
__all__ = ["NodeCacheOps"]
