# ====== Code Summary ======
# MetadataValueApi — read-only access to the DISTINCT stored values of one metadata field. A field's
# values live as JSONB in `document_metadata` (document scope) or `chunk_metadata` (chunk scope), each
# value either a scalar or a list (keyword_list); every query here explodes both shapes into one text
# element stream (`jsonb_array_elements_text` over the value, a scalar wrapped into a 1-item array),
# filtered by `field_id` (which already scopes to one collection). Every query is bounded (a LIMIT or
# a per-value window) or is a single aggregate — never an unbounded row fetch into Python. Ties sort
# by byte order (COLLATE "C") so results are deterministic whatever the database locale.

# ====== Standard Library Imports ======
import uuid
from collections.abc import Sequence
from typing import Any

# ====== Third-Party Library Imports ======
from sqlalchemy import Text, bindparam, select, text
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.ext.asyncio import AsyncSession

# ====== Internal Project Imports ======
from shared_libs.public_models import FieldScope

# ====== Local Project Imports ======
from ..tables import DocumentMetadata

# The value table each scope stores its values in — a closed whitelist, so the table name formatted
# into the SQL below is never caller-controlled.
_SCOPE_TABLES: dict[FieldScope, str] = {
    FieldScope.DOCUMENT: "document_metadata",
    FieldScope.CHUNK: "chunk_metadata",
}

# One text element per stored value (scalar) or per list item (keyword_list); JSON nulls are dropped.
_ELEMENTS_SQL = """
    SELECT elem
    FROM {table} AS m
    CROSS JOIN LATERAL jsonb_array_elements_text(
        CASE WHEN jsonb_typeof(m.value) = 'array' THEN m.value ELSE jsonb_build_array(m.value) END
    ) AS elem
    WHERE m.field_id = :field_id AND elem IS NOT NULL
"""


class MetadataValueApi:
    """Static, bounded reads of a metadata field's distinct stored values."""

    def __new__(cls, *args: object, **kwargs: object) -> None:
        raise TypeError("MetadataValueApi is a static-only class and cannot be instantiated.")

    @staticmethod
    def _elements(scope: FieldScope) -> str:
        """Return the element-stream subquery for a scope's value table."""
        # 1. Resolve the scope's table from the closed whitelist (KeyError on an unknown scope).
        return _ELEMENTS_SQL.format(table=_SCOPE_TABLES[FieldScope(scope)])

    @staticmethod
    async def case_insensitive_matches(
        session: AsyncSession,
        field_id: int,
        scope: FieldScope,
        lowered: Sequence[str],
        per_value_limit: int,
    ) -> list[str]:
        """
        Return the distinct stored values whose lowercase form is one of ``lowered``.

        The cap applies PER requested value (a window over each lowercase form), never to the whole
        batch — a global LIMIT ordered by value would truncate the late values of a large batch and
        report them as unmatched.

        Args:
            session (AsyncSession): The open session.
            field_id (int): The metadata field (collection-scoped) to read.
            scope (FieldScope): Where the field's values live (document or chunk table).
            lowered (Sequence[str]): The already-lowercased values to match.
            per_value_limit (int): Cap on the number of variants returned for each requested value.

        Returns:
            list[str]: The exact stored variants (e.g. ``AFD-P0153`` and ``afd-P0153``), sorted.
        """
        # 1. One batched query for every requested value, capped per lowercase form by a window.
        sql = text(
            "SELECT r.elem FROM ("
            "SELECT e.elem, row_number() OVER ("
            'PARTITION BY lower(e.elem) ORDER BY e.elem COLLATE "C") AS rank '
            f"FROM ({MetadataValueApi._elements(scope)}) AS e "
            "WHERE lower(e.elem) = ANY(:needles) GROUP BY e.elem"
            ') AS r WHERE r.rank <= :per_value ORDER BY r.elem COLLATE "C"'
        ).bindparams(bindparam("needles", type_=ARRAY(Text)))
        result = await session.execute(
            sql, {"field_id": field_id, "needles": list(lowered), "per_value": per_value_limit}
        )
        return [row[0] for row in result]

    @staticmethod
    async def containing(
        session: AsyncSession, field_id: int, scope: FieldScope, needle: str, limit: int
    ) -> list[str]:
        """
        Return distinct stored values containing ``needle`` case-insensitively, best first.

        Ordering: values STARTING with the needle first, then by frequency, then the shortest.

        Args:
            session (AsyncSession): The open session.
            field_id (int): The metadata field to read.
            scope (FieldScope): Where the field's values live.
            needle (str): The lowercased substring to look for.
            limit (int): Cap on the number of returned values.

        Returns:
            list[str]: The matching stored values, best first.
        """
        # 1. strpos instead of LIKE so a '%' or '_' in the user value needs no escaping.
        sql = text(
            f"SELECT e.elem FROM ({MetadataValueApi._elements(scope)}) AS e "
            "WHERE strpos(lower(e.elem), :needle) > 0 GROUP BY e.elem "
            "ORDER BY (strpos(lower(e.elem), :needle) = 1) DESC, count(*) DESC, "
            'length(e.elem), e.elem COLLATE "C" LIMIT :limit'
        )
        result = await session.execute(
            sql, {"field_id": field_id, "needle": needle, "limit": limit}
        )
        return [row[0] for row in result]

    @staticmethod
    async def pattern_matches(
        session: AsyncSession,
        field_id: int,
        scope: FieldScope,
        needle: str,
        *,
        prefix: bool,
        limit: int,
    ) -> list[str]:
        """
        Return the distinct stored values containing (or starting with) ``needle``, ignoring case.

        Both sides are lowercased IN SQL, and the match uses ``strpos`` / ``starts_with`` rather
        than ``LIKE`` — a ``%`` or ``_`` in the user value is a literal character, with no
        escaping to get wrong. Every case variant comes back as its own value (each is a distinct
        stored spelling a Qdrant exact match must name).

        Args:
            session (AsyncSession): The open session.
            field_id (int): The metadata field to read.
            scope (FieldScope): Where the field's values live.
            needle (str): The user substring / prefix (any case).
            prefix (bool): True → values STARTING with the needle; False → values CONTAINING it.
            limit (int): Cap on the number of returned values (callers ask cap + 1 to detect
                overflow).

        Returns:
            list[str]: The matching stored values, most frequent first (ties by byte order).
        """
        # 1. One bounded, grouped query over the element stream.
        predicate = (
            "starts_with(lower(e.elem), lower(:needle))"
            if prefix
            else "strpos(lower(e.elem), lower(:needle)) > 0"
        )
        sql = text(
            f"SELECT e.elem FROM ({MetadataValueApi._elements(scope)}) AS e "
            f"WHERE {predicate} GROUP BY e.elem "
            'ORDER BY count(*) DESC, e.elem COLLATE "C" LIMIT :limit'
        )
        result = await session.execute(
            sql, {"field_id": field_id, "needle": needle, "limit": limit}
        )
        return [row[0] for row in result]

    @staticmethod
    async def top_values(
        session: AsyncSession, field_id: int, scope: FieldScope, limit: int
    ) -> list[str]:
        """
        Return the field's distinct stored values, most frequent first.

        Args:
            session (AsyncSession): The open session.
            field_id (int): The metadata field to read.
            scope (FieldScope): Where the field's values live.
            limit (int): Cap on the number of returned values.

        Returns:
            list[str]: Up to ``limit`` distinct values by descending frequency (ties by value).
        """
        # 1. Group the element stream and keep the most frequent values.
        sql = text(
            f"SELECT e.elem FROM ({MetadataValueApi._elements(scope)}) AS e "
            'GROUP BY e.elem ORDER BY count(*) DESC, e.elem COLLATE "C" LIMIT :limit'
        )
        result = await session.execute(sql, {"field_id": field_id, "limit": limit})
        return [row[0] for row in result]

    @staticmethod
    async def distinct_count(session: AsyncSession, field_id: int, scope: FieldScope) -> int:
        """
        Count the field's distinct stored values (list items counted individually).

        Args:
            session (AsyncSession): The open session.
            field_id (int): The metadata field to read.
            scope (FieldScope): Where the field's values live.

        Returns:
            int: The number of distinct stored values.
        """
        # 1. A single aggregate over the element stream.
        sql = text(f"SELECT count(DISTINCT e.elem) FROM ({MetadataValueApi._elements(scope)}) AS e")
        result = await session.execute(sql, {"field_id": field_id})
        return int(result.scalar_one())

    @staticmethod
    async def document_values(
        session: AsyncSession, field_id: int, document_ids: Sequence[uuid.UUID]
    ) -> dict[uuid.UUID, Any]:
        """
        Return one document-scope field's raw value for each of the given documents.

        Args:
            session (AsyncSession): The open session.
            field_id (int): The document-scope metadata field to read.
            document_ids (Sequence[uuid.UUID]): The documents to read it for.

        Returns:
            dict[uuid.UUID, Any]: document id → stored JSONB value (absent when unset).
        """
        # 1. Nothing asked → no round trip.
        if not document_ids:
            return {}
        # 2. One batched read keyed by the (field_id, document_id) composite index.
        stmt = select(DocumentMetadata.document_id, DocumentMetadata.value).where(
            DocumentMetadata.field_id == field_id,
            DocumentMetadata.document_id.in_(list(document_ids)),
        )
        result = await session.execute(stmt)
        return {row.document_id: row.value for row in result}


__all__ = ["MetadataValueApi"]
