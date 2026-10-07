# ====== Code Summary ======
# QdrantFieldPurgeApi — the collection-wide cleanup of a metadata field that left the schema
# (removed, or renamed away — and not reused by the post-change schema). A field's denormalised
# footprint on the chunk points is keyed by its NAME: its payload key (+ payload index) when
# filterable, its ``meta_<slug>_dense`` / ``meta_<slug>_bm25`` named vectors when semantic/lexical. This finds that residue — the explicit
# names plus anything the store still carries for a name the schema no longer has (so a cleanup that
# failed once is healed by the next one) — and clears it from EVERY point with filter-based, server-side
# ops (one request each, whatever the point count). The named-vector DECLARATIONS stay (Qdrant cannot
# drop a named vector from a live collection); only their data is removed.

# ====== Standard Library Imports ======
from collections.abc import Collection

# ====== Third-Party Library Imports ======
from qdrant_client import AsyncQdrantClient, models

# ====== Local Project Imports ======
from ..vectors import RESERVED_PAYLOAD_KEYS, VectorNames
from .collection_api import QdrantCollectionApi

# The prefix/suffixes of a metadata field's named vectors (see VectorNames) — anything else declared
# on the collection (the content vectors) is never residue.
_META_PREFIX = "meta_"
_META_SUFFIXES = ("_dense", "_bm25")


class QdrantFieldPurgeApi:
    """Static collection-wide cleanup of the payload keys / meta vectors of departed fields."""

    def __new__(cls, *args: object, **kwargs: object) -> None:
        raise TypeError("QdrantFieldPurgeApi is a static-only class and cannot be instantiated.")

    @staticmethod
    def _field_vectors(field_names: Collection[str]) -> set[str]:
        """Return every meta vector name the given fields could own (dense + sparse)."""
        return {VectorNames.field_dense(name) for name in field_names} | {
            VectorNames.field_sparse(name) for name in field_names
        }

    @classmethod
    async def residue(
        cls,
        client: AsyncQdrantClient,
        name: str,
        *,
        departed: Collection[str],
        current: Collection[str],
    ) -> tuple[set[str], set[str], set[str]]:
        """
        Compute what to clear: payload keys, the indexed subset of them, and declared meta vectors.

        Args:
            client (AsyncQdrantClient): The connection from QdrantClient.raw.
            name (str): The Qdrant collection name (must exist — the caller guards it).
            departed (Collection[str]): Field names that just left the schema — their payload keys
                are purged (even an un-indexed key the residue scan cannot see) unless ``current``
                has them again.
            current (Collection[str]): The field names the schema has NOW (never purged as residue).

        Returns:
            tuple[set[str], set[str], set[str]]: (payload keys to delete, indexed keys to un-index,
                declared meta vectors whose data to delete).
        """
        # 1. Payload side: the explicit names + any indexed key the schema no longer has — but NEVER a
        #    name the post-change schema has (a swap / a reused name is a live field: its payload is
        #    repainted by the backfill, never blanked here).
        info = await client.get_collection(name)
        indexed = set((info.payload_schema or {}).keys())
        live = RESERVED_PAYLOAD_KEYS | set(current)
        payload_keys = (set(departed) | indexed) - live

        # 2. Vector side: declared meta vectors owned by no CURRENT field. Vector names are slugs, so a
        #    rename that keeps the slug ("Author" → "author") keeps valid vectors — a vector a current
        #    field owns is never purged, even when a departed name maps to it.
        dense, sparse = await QdrantCollectionApi.declared_vectors(client, name)
        declared_meta = {
            vector
            for vector in dense | sparse
            if vector.startswith(_META_PREFIX) and vector.endswith(_META_SUFFIXES)
        }
        vectors = declared_meta - cls._field_vectors(current)
        return payload_keys, payload_keys & indexed, vectors

    @staticmethod
    async def purge(
        client: AsyncQdrantClient,
        name: str,
        *,
        payload_keys: Collection[str],
        indexed_keys: Collection[str],
        vector_names: Collection[str],
    ) -> None:
        """
        Clear the given payload keys / indexes / named-vector data from EVERY point of a collection.

        An empty ``Filter()`` selects all points, so each op is a single server-side request
        regardless of the collection size. Idempotent: clearing an absent key/vector is a no-op.

        Args:
            client (AsyncQdrantClient): The connection from QdrantClient.raw.
            name (str): The Qdrant collection name (must exist — the caller guards it).
            payload_keys (Collection[str]): Payload keys to delete from every point.
            indexed_keys (Collection[str]): Payload indexes to drop (subset of ``payload_keys``).
            vector_names (Collection[str]): DECLARED named vectors whose data to delete.
        """
        # 1. Payload keys first (what a filter matches on), then their now-useless indexes.
        if payload_keys:
            await client.delete_payload(
                collection_name=name, keys=sorted(payload_keys), points=models.Filter()
            )
        for key in sorted(indexed_keys):
            await client.delete_payload_index(collection_name=name, field_name=key)

        # 2. The meta vectors' data (declarations stay — a live collection cannot drop them).
        if vector_names:
            await client.delete_vectors(
                collection_name=name, vectors=sorted(vector_names), points=models.Filter()
            )


__all__ = ["QdrantFieldPurgeApi"]
