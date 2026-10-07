# ====== Code Summary ======
# MetadataValueResolver — Postgres as the VALUE ORACLE of a collection's metadata fields. Given a field
# spec (its collection-scoped row) and user value(s), it resolves against the field's DISTINCT stored
# values: `canonicalize` maps a value to the exact stored variants matching it case-insensitively (so a
# search filter can then match those canonical values exactly in Qdrant), `suggest` ranks the closest
# stored values for a "did you mean" hint, and `distinct_values` / `distinct_count` describe a field.
# Every read is a bounded query (LIMIT or a single aggregate); the similarity fallback runs Python
# difflib on a bounded, frequency-ordered pool (no pg_trgm dependency — the extension is not installed).

# ====== Standard Library Imports ======
import difflib
import uuid
from collections.abc import Sequence
from typing import Any

# ====== Third-Party Library Imports ======
from loggerplusplus import LoggerClass

# ====== Internal Project Imports ======
from shared_libs.services.db.postgresql import PostgresClient
from shared_libs.services.db.postgresql.apis import MetadataValueApi
from shared_libs.services.db.postgresql.tables import MetadataField

# Cap on the stored case variants returned PER requested value (a value has a handful at most; the cap
# only guards a pathological field — applied per value so a large batch never loses its late values).
_VARIANTS_PER_VALUE = 20
# Size of the frequency-ordered pool the difflib similarity fallback ranks over.
_SIMILARITY_POOL = 2000
# Minimum difflib ratio for a value to count as "close" (0.6 is difflib's own default).
_SIMILARITY_CUTOFF = 0.6


class MetadataValueResolver(LoggerClass):
    """Resolve user values against a metadata field's distinct stored values (case-insensitive)."""

    def __init__(self, postgres: PostgresClient) -> None:
        """
        Args:
            postgres (PostgresClient): The tabular truth store.
        """
        LoggerClass.__init__(self)
        self._postgres = postgres

    async def canonicalize(
        self, field: MetadataField, values: str | Sequence[str]
    ) -> dict[str, list[str]]:
        """
        Map each user value to the stored values equal to it ignoring case.

        Args:
            field (MetadataField): The field (its ``id`` + ``scope`` locate the stored values).
            values (str | Sequence[str]): One value or several (resolved in ONE query).

        Returns:
            dict[str, list[str]]: user value → its exact stored variants (sorted); an empty list when
            no stored value matches even case-insensitively.
        """
        # 1. Normalise the input to a de-duplicated list (a single value is a 1-item batch).
        requested = [values] if isinstance(values, str) else list(dict.fromkeys(values))
        if not requested:
            return {}

        # 2. One batched query over the lowercase forms (variants capped per value, not per batch).
        async with self._postgres.session() as session:
            stored = await MetadataValueApi.case_insensitive_matches(
                session,
                field.id,
                field.scope,
                list({value.lower() for value in requested}),
                _VARIANTS_PER_VALUE,
            )

        # 3. Group the stored variants back under each requested value.
        return {
            value: [variant for variant in stored if variant.lower() == value.lower()]
            for value in requested
        }

    async def suggest(self, field: MetadataField, value: str, k: int = 5) -> list[str]:
        """
        Rank the stored values closest to ``value`` (for a "did you mean" hint).

        Containment first (values starting with, then containing, the input — case-insensitive),
        then a difflib similarity ranking over a bounded frequency-ordered pool.

        Args:
            field (MetadataField): The field to suggest values of.
            value (str): The user value that matched nothing.
            k (int): Maximum number of suggestions.

        Returns:
            list[str]: Up to ``k`` stored values, closest first (empty when the field has none).
        """
        # 1. Containment matches — the strongest, cheapest signal.
        needle = value.strip().lower()
        async with self._postgres.session() as session:
            ranked = (
                await MetadataValueApi.containing(session, field.id, field.scope, needle, k)
                if needle
                else []
            )
            # 2. Fill the remaining slots by similarity over a bounded pool (only when needed).
            if len(ranked) < k:
                pool = await MetadataValueApi.top_values(
                    session, field.id, field.scope, _SIMILARITY_POOL
                )
                ranked += self.__similar(needle, pool, k)

        # 3. De-duplicate (containment and similarity can agree), keep order, cap at k.
        return list(dict.fromkeys(ranked))[:k]

    async def distinct_values(self, field: MetadataField, limit: int = 10) -> list[str]:
        """
        Return the field's distinct stored values, most frequent first.

        Args:
            field (MetadataField): The field to describe.
            limit (int): Maximum number of values.

        Returns:
            list[str]: Up to ``limit`` distinct values (list items counted individually).
        """
        # 1. A single bounded, grouped query.
        async with self._postgres.session() as session:
            return await MetadataValueApi.top_values(session, field.id, field.scope, limit)

    async def distinct_count(self, field: MetadataField) -> int:
        """
        Count the field's distinct stored values.

        Args:
            field (MetadataField): The field to describe.

        Returns:
            int: The number of distinct stored values (list items counted individually).
        """
        # 1. A single aggregate.
        async with self._postgres.session() as session:
            return await MetadataValueApi.distinct_count(session, field.id, field.scope)

    async def document_values(
        self, field: MetadataField, document_ids: Sequence[uuid.UUID]
    ) -> dict[uuid.UUID, Any]:
        """
        Return a document-scope field's raw value for each of the given documents (one batch read).

        Args:
            field (MetadataField): The document-scope field to read.
            document_ids (Sequence[uuid.UUID]): The documents to read it for.

        Returns:
            dict[uuid.UUID, Any]: document id → stored value (absent when the document has none).
        """
        # 1. One batched read for the whole set.
        async with self._postgres.session() as session:
            return await MetadataValueApi.document_values(session, field.id, document_ids)

    @staticmethod
    def __similar(needle: str, pool: Sequence[str], k: int) -> list[str]:
        """Rank ``pool`` by difflib similarity to ``needle`` (case-insensitive), closest first."""
        # 1. Compare lowercase forms; map each lowercase match back to its first stored spelling.
        by_lower: dict[str, str] = {}
        for stored in pool:
            by_lower.setdefault(stored.lower(), stored)
        close = difflib.get_close_matches(needle, list(by_lower), n=k, cutoff=_SIMILARITY_CUTOFF)
        return [by_lower[match] for match in close]


__all__ = ["MetadataValueResolver"]
