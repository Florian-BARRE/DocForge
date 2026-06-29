# ====== Code Summary ======
# ChunkRepository: Postgres persistence for semantic chunks produced by S4/S5.
# Chunks are the atomic retrieval units; they mirror Qdrant points and are the source of
# truth for raw_text and provenance returned to callers after top-k retrieval.

# ====== Standard Library Imports ======
from __future__ import annotations

import json
import uuid

# ====== Third-Party Library Imports ======
from loggerplusplus import LoggerClass
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

# ====== Internal Project Imports ======
from common_libs.domain.ir.chunk import Chunk


class ChunkRepository(LoggerClass):
    """
    Postgres repository for the ``chunk`` table.

    All methods accept an ``AsyncSession`` injected by the caller — the repository
    never opens its own connection (follows the Unit-of-Work pattern).

    Split decision (P4 god-class review):
        DOCUMENTED EXCEPTION — no ``ChunkRepoHelpers`` extracted.

        Rationale: every method in this class is session-bound and issues SQL via
        ``AsyncSession.execute(text(...))``.  The only non-trivial pure logic is the
        row-dict comprehension and sort in ``bulk_insert`` (~10 lines).  Extracting
        those into a static helper would create an artificial boundary with no
        meaningful cohesion benefit and would add indirection without reducing
        complexity.  The file sits at 284 lines — above the 200-line soft limit but
        within the 300-line threshold that warrants a real split.  All methods belong
        to a single, well-defined responsibility (chunk persistence).  Leave as one
        file.
    """

    def __init__(self) -> None:
        """Initialize the repository."""
        LoggerClass.__init__(self)

    async def bulk_insert(
        self,
        session: AsyncSession,
        chunks: list[Chunk],
    ) -> None:
        """
        Bulk-insert a list of chunks into the ``chunk`` table.

        Uses a single-statement multi-row insert for efficiency.

        Idempotency-contract shift (vs the P4 ``ON CONFLICT DO NOTHING``): a re-ingest with the
        same chunk id now UPDATEs the re-derivable columns — ``derived_meta`` (S5b output) and
        ``embed_text`` (S5 output) — so editing a metagen prompt / contextualization template and
        re-running refreshes those values in place. The chunk id (UUID v5 of doc+blocks+config_hash)
        and its immutable structural columns are unchanged on conflict, so this stays a safe superset
        of the old behavior. S6's Qdrant upsert remains the indexing idempotency mechanism.

        Args:
            session (AsyncSession): Active SQLAlchemy async session.
            chunks (list[Chunk]): Chunks to persist.

        Returns:
            None
        """
        if not chunks:
            return

        # 1. Build parameterized multi-row insert.
        #    Parents must land before children so the self FK (parent_id → id) is satisfiable
        #    inside the single statement — sort parents (parent_id is None) first.
        ordered = sorted(chunks, key=lambda c: c.parent_id is not None)
        rows = [
            {
                "id": c.id,
                "document_id": c.document_id,
                "config_hash": c.config_hash,
                "block_ids": c.block_ids,          # list[str] — PostgreSQL text[]
                "raw_text": c.raw_text,
                "embed_text": c.embed_text,
                "token_count": c.token_count,
                "strategy": c.strategy,
                "prov": json.dumps(c.prov),
                "derived_meta": json.dumps(c.derived_meta),
                "parent_id": c.parent_id,
            }
            for c in ordered
        ]

        await session.execute(
            text(
                """
                INSERT INTO chunk
                    (id, document_id, config_hash, block_ids,
                     raw_text, embed_text, token_count, strategy, prov, derived_meta, parent_id)
                VALUES
                    (:id, :document_id, :config_hash, :block_ids,
                     :raw_text, :embed_text, :token_count, :strategy,
                     CAST(:prov AS jsonb), CAST(:derived_meta AS jsonb), :parent_id)
                ON CONFLICT (id) DO UPDATE SET
                    derived_meta = EXCLUDED.derived_meta,
                    embed_text = EXCLUDED.embed_text
                """
            ),
            rows,
        )
        await session.commit()
        self.logger.debug(f"ChunkRepository: inserted {len(chunks)} chunk(s).")

    async def update(
        self,
        session: AsyncSession,
        chunk_id: str,
        *,
        raw_text: str | None = None,
        embed_text: str | None = None,
    ) -> dict | None:
        """
        Update a chunk's text fields (partial — None leaves a field unchanged).

        Args:
            session (AsyncSession): Active session.
            chunk_id (str): Chunk primary key.
            raw_text (str | None): New display/citation text, or None to keep.
            embed_text (str | None): New contextualized embed text, or None to keep.

        Returns:
            dict | None: The updated row, or None if the chunk does not exist.
        """
        result = await session.execute(
            text(
                """
                UPDATE chunk SET
                    raw_text = COALESCE(:raw_text, raw_text),
                    embed_text = COALESCE(:embed_text, embed_text)
                WHERE id = :chunk_id
                RETURNING id, document_id, config_hash, block_ids,
                          raw_text, embed_text, token_count, strategy, prov, derived_meta, parent_id
                """
            ),
            {"chunk_id": chunk_id, "raw_text": raw_text, "embed_text": embed_text},
        )
        row = result.mappings().first()
        await session.commit()
        return dict(row) if row is not None else None

    async def get_by_id(
        self,
        session: AsyncSession,
        chunk_id: str,
    ) -> dict | None:
        """
        Fetch a single chunk row by primary key.

        Args:
            session (AsyncSession): Active SQLAlchemy async session.
            chunk_id (str): UUID string of the chunk.

        Returns:
            dict | None: Row as a dictionary, or None if not found.
        """
        result = await session.execute(
            text(
                """
                SELECT id, document_id, config_hash, block_ids,
                       raw_text, embed_text, token_count, strategy, prov, derived_meta, parent_id
                FROM chunk
                WHERE id = :chunk_id
                """
            ),
            {"chunk_id": chunk_id},
        )
        row = result.mappings().first()
        return dict(row) if row is not None else None

    async def get_by_ids(
        self,
        session: AsyncSession,
        chunk_ids: list[str],
    ) -> dict[str, dict]:
        """
        Fetch many chunk rows by primary key in a single query.

        Used by hierarchical retrieval to hydrate hit children and roll them up to their
        parents without issuing one query per id.

        Args:
            session (AsyncSession): Active SQLAlchemy async session.
            chunk_ids (list[str]): UUID strings of the chunks to fetch.

        Returns:
            dict[str, dict]: Mapping ``chunk_id → row dict`` (missing ids are simply absent).
        """
        # 1. Empty input → no query
        if not chunk_ids:
            return {}

        # 2. Single ANY(:ids) lookup keyed by id
        result = await session.execute(
            text(
                """
                SELECT id, document_id, config_hash, block_ids,
                       raw_text, embed_text, token_count, strategy, prov, derived_meta, parent_id
                FROM chunk
                WHERE id = ANY(:ids)
                """
            ),
            {"ids": [str(cid) for cid in chunk_ids]},
        )
        return {str(row["id"]): dict(row) for row in result.mappings().all()}

    async def get_by_document(
        self,
        session: AsyncSession,
        document_id: str | uuid.UUID,
        config_hash: str | None = None,
    ) -> list[dict]:
        """
        Fetch all chunks for a document, optionally filtered by config_hash.

        Args:
            session (AsyncSession): Active SQLAlchemy async session.
            document_id (str | UUID): Owning document's UUID.
            config_hash (str | None): If given, filter to chunks from this config version.

        Returns:
            list[dict]: List of chunk rows as dictionaries, ordered by position.
        """
        # 1. Build query — optionally add config_hash filter
        if config_hash is not None:
            result = await session.execute(
                text(
                    """
                    SELECT id, document_id, config_hash, block_ids,
                           raw_text, embed_text, token_count, strategy, prov, derived_meta, parent_id
                    FROM chunk
                    WHERE document_id = :doc_id AND config_hash = :config_hash
                    ORDER BY (prov->>'pages')::text
                    """
                ),
                {"doc_id": str(document_id), "config_hash": config_hash},
            )
        else:
            result = await session.execute(
                text(
                    """
                    SELECT id, document_id, config_hash, block_ids,
                           raw_text, embed_text, token_count, strategy, prov, derived_meta, parent_id
                    FROM chunk
                    WHERE document_id = :doc_id
                    ORDER BY (prov->>'pages')::text
                    """
                ),
                {"doc_id": str(document_id)},
            )

        return [dict(row) for row in result.mappings().all()]

    async def count_by_document(
        self,
        session: AsyncSession,
        document_id: str | uuid.UUID,
    ) -> int:
        """
        Count the number of chunks belonging to a document.

        Args:
            session (AsyncSession): Active SQLAlchemy async session.
            document_id (str | UUID): Owning document's UUID.

        Returns:
            int: Total chunk count for the document (0 if none).
        """
        result = await session.execute(
            text("SELECT COUNT(*) FROM chunk WHERE document_id = :doc_id"),
            {"doc_id": str(document_id)},
        )
        return int(result.scalar_one() or 0)

    async def delete_by_document(
        self,
        session: AsyncSession,
        document_id: str | uuid.UUID,
    ) -> int:
        """
        Delete all chunks for a document (used before reindex).

        Args:
            session (AsyncSession): Active SQLAlchemy async session.
            document_id (str | UUID): Owning document's UUID.

        Returns:
            int: Number of rows deleted.
        """
        result = await session.execute(
            text("DELETE FROM chunk WHERE document_id = :doc_id"),
            {"doc_id": str(document_id)},
        )
        await session.commit()
        n = result.rowcount
        self.logger.debug(f"ChunkRepository: deleted {n} chunk(s) for doc={document_id}.")
        return n
