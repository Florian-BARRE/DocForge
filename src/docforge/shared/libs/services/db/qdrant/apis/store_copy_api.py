# ====== Code Summary ======
# QdrantStoreCopyApi — the point-copy primitives of an index rebuild: read the old store's content
# dense dimension and payload indexes, scroll its points (vectors + payload) in batches, and upsert a
# batch into the new store keeping ONLY the vector names the new store declares. Every metadata BM25
# vector (``meta_*_bm25``) is DROPPED on copy: the old ones may hold BGE-M3 sparse weights while the
# new store declares them with the IDF modifier (local BM25 encoding) — copying would mix encoders.
# The post-swap meta-vector backfill re-fills them from Postgres — DOCUMENT-scope only, which is why a
# collection with a (legacy) chunk-scope lexical field is refused at admission (409
# ``rebuild_unsupported_chunk_lexical``): its chunk BM25 vectors would be dropped and never refilled.

# ====== Standard Library Imports ======
from collections.abc import AsyncIterator

# ====== Third-Party Library Imports ======
from qdrant_client import AsyncQdrantClient, models

# ====== Local Project Imports ======
from ..vectors import VectorNames


class QdrantStoreCopyApi:
    """Static scroll/copy helpers used by the rebuild_index job."""

    def __new__(cls, *args: object, **kwargs: object) -> None:
        raise TypeError("QdrantStoreCopyApi is a static-only class and cannot be instantiated.")

    @staticmethod
    async def content_dense_dim(client: AsyncQdrantClient, name: str) -> int:
        """
        Return the size of the store's ``content_dense`` vector (the rebuilt store keeps it).

        Raises:
            ValueError: When the store declares no ``content_dense`` vector.
        """
        vectors = (await client.get_collection(name)).config.params.vectors
        params = vectors.get(VectorNames.CONTENT_DENSE) if isinstance(vectors, dict) else None
        if params is None:
            raise ValueError(f"Qdrant collection '{name}' declares no content_dense vector")
        return int(params.size)

    @staticmethod
    async def payload_indexes(
        client: AsyncQdrantClient, name: str
    ) -> dict[str, models.PayloadSchemaType]:
        """Return the store's payload indexes as ``key → data type``."""
        schema = (await client.get_collection(name)).payload_schema or {}
        return {key: info.data_type for key, info in schema.items()}

    @classmethod
    async def copy_missing_indexes(
        cls, client: AsyncQdrantClient, source: str, target: str
    ) -> list[str]:
        """
        Re-create on ``target`` every payload index ``source`` has and ``target`` lacks.

        Keeps any index the schema-driven create did not derive (a legacy/system index) — the rebuilt
        store never filters worse than the old one.

        Returns:
            list[str]: The payload keys indexed by this call.
        """
        # 1. Diff the two stores' index sets; create only the missing ones.
        existing = await cls.payload_indexes(client, target)
        added: list[str] = []
        for key, data_type in (await cls.payload_indexes(client, source)).items():
            if key not in existing:
                await client.create_payload_index(
                    collection_name=target, field_name=key, field_schema=data_type
                )
                added.append(key)
        return added

    @staticmethod
    async def scroll(
        client: AsyncQdrantClient, name: str, batch_size: int
    ) -> AsyncIterator[list[models.Record]]:
        """Yield every point of a store (vectors + payload) in batches of ``batch_size``."""
        offset = None
        while True:
            records, offset = await client.scroll(
                collection_name=name,
                limit=batch_size,
                offset=offset,
                with_payload=True,
                with_vectors=True,
            )
            if records:
                yield records
            if offset is None:
                return

    @staticmethod
    def vector_names(records: list[models.Record]) -> set[str]:
        """Every named vector at least one scrolled record carries."""
        return {
            key for record in records if isinstance(record.vector, dict) for key in record.vector
        }

    @staticmethod
    def keep_vector(vector_name: str, declared: set[str]) -> bool:
        """Whether a copied vector survives: declared by the new store AND not a meta BM25 vector."""
        return vector_name in declared and not VectorNames.is_field_sparse(vector_name)

    @classmethod
    def to_points(
        cls, records: list[models.Record], declared: set[str]
    ) -> list[models.PointStruct]:
        """Map scrolled records to upsertable points, filtering their named vectors."""
        points: list[models.PointStruct] = []
        for record in records:
            vectors = record.vector if isinstance(record.vector, dict) else {}
            kept = {key: value for key, value in vectors.items() if cls.keep_vector(key, declared)}
            points.append(models.PointStruct(id=record.id, vector=kept, payload=record.payload))
        return points

    @classmethod
    async def upsert_batch(
        cls,
        client: AsyncQdrantClient,
        target: str,
        records: list[models.Record],
        declared: set[str],
    ) -> int:
        """Upsert one scrolled batch into ``target`` (filtered vectors); return the point count."""
        points = cls.to_points(records, declared)
        await client.upsert(collection_name=target, points=points, wait=True)
        return len(points)


__all__ = ["QdrantStoreCopyApi"]
