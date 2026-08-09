# ====== Code Summary ======
# StorageFootprintFacade — the on-demand answer to "how much hardware does this collection occupy,
# per store?". It runs a handful of grouped aggregate queries (S3 exact, Postgres estimated) and a
# few count/sample Qdrant calls (estimated), then assembles the per-store totals AND the per-document
# breakdown (sorted descending, so it doubles as the top-N). No caching, no per-document N+1: one
# grouped SQL per store dimension, one facet call for per-document point counts. A collection never
# embedded (no Qdrant space) reports zero vectors instead of raising — mirroring the delete guard.

# ====== Standard Library Imports ======
import uuid

# ====== Internal Project Imports ======
from loggerplusplus import LoggerClass

from shared_libs.services.db.postgresql import PostgresClient
from shared_libs.services.db.postgresql.apis import StorageFootprintApi
from shared_libs.services.db.qdrant import QdrantClient, VectorNames
from shared_libs.services.db.qdrant.apis import QdrantProfile, QdrantStorageApi

# ====== Local Project Imports ======
from .helpers import DatabaseHelpers
from .storage_footprint_helpers import StorageFootprintHelpers
from .storage_footprint_payloads import (
    CollectionFootprint,
    DocumentFootprint,
    PostgresFootprint,
    QdrantFootprint,
    S3Footprint,
)


class StorageFootprintFacade(LoggerClass):
    """Composes a collection's material footprint (S3 exact, Postgres + Qdrant estimated)."""

    def __init__(self, postgres: PostgresClient, qdrant: QdrantClient) -> None:
        """
        Args:
            postgres (PostgresClient): The tabular truth store (blob sizes + row-byte estimates).
            qdrant (QdrantClient): The vector store (point counts + shape sample).
        """
        LoggerClass.__init__(self)
        self._postgres = postgres
        self._qdrant = qdrant

    def __s3_footprint(self, original: int, rendered: int, physical_unique: int) -> S3Footprint:
        """Build an S3 footprint from its parts (``physical_unique`` == total at document level)."""
        return S3Footprint(
            original_bytes=original,
            rendered_bytes=rendered,
            total_bytes=original + rendered,
            physical_unique_bytes=physical_unique,
        )

    def __dense_carriers(self, content_points: int, meta_points: dict[str, int]) -> dict[str, int]:
        """Named dense vector → its carrier point count: content on every point, meta on its own."""
        # content_dense rides every point; each meta vector rides only its field's carrier points.
        points_by_vector = {VectorNames.CONTENT_DENSE: content_points}
        points_by_vector.update(meta_points)
        return points_by_vector

    def __qdrant_footprint(
        self, points: int, points_by_vector: dict[str, int], profile: QdrantProfile | None
    ) -> QdrantFootprint:
        """Estimate a point set's vector bytes — dense weighted PER named vector by its carrier count."""
        # A collection with no Qdrant space yet has no shape to multiply — everything is zero.
        if profile is None:
            return QdrantFootprint(0, 0, 0, 0, 0)
        dense = StorageFootprintHelpers.dense_bytes(points_by_vector, profile.dense_dims)
        return StorageFootprintHelpers.qdrant_footprint(
            points=points,
            dense_bytes=dense,
            avg_sparse_entries=profile.avg_sparse_entries,
            avg_payload_bytes=profile.avg_payload_bytes,
        )

    def __build_documents(
        self,
        names: list[tuple[uuid.UUID, str]],
        pg_by_doc: dict[uuid.UUID, dict[str, int]],
        s3_by_doc: dict[uuid.UUID, tuple[int, int]],
        doc_fields: dict[uuid.UUID, set[str]],
        profile: QdrantProfile | None,
    ) -> list[DocumentFootprint]:
        """Assemble every document's footprint and sort the list by total bytes, descending."""
        # 1. One footprint per document — an absent store simply contributes an all-zero section.
        documents: list[DocumentFootprint] = []
        for document_id, filename in names:
            original, rendered = s3_by_doc.get(document_id, (0, 0))
            s3 = self.__s3_footprint(original, rendered, original + rendered)
            postgres = StorageFootprintHelpers.postgres_footprint(pg_by_doc.get(document_id, {}))
            points = 0 if profile is None else profile.per_document_points.get(str(document_id), 0)
            # A document-scope meta vector rides ALL of the document's points; so each semantic field
            # the document populates carries this document's own point count.
            meta_points = {
                VectorNames.field_dense(field): points
                for field in doc_fields.get(document_id, set())
            }
            qdrant = self.__qdrant_footprint(
                points, self.__dense_carriers(points, meta_points), profile
            )
            total = s3.total_bytes + postgres.total_bytes + qdrant.total_bytes
            documents.append(
                DocumentFootprint(
                    document_id=document_id,
                    filename=filename,
                    s3=s3,
                    postgres=postgres,
                    qdrant=qdrant,
                    total_bytes=total,
                )
            )

        # 2. Heaviest first — the breakdown doubles as the top-N.
        documents.sort(key=lambda doc: doc.total_bytes, reverse=True)
        return documents

    def __collection_postgres(
        self, pg_rows: list[tuple[uuid.UUID | None, str, int]]
    ) -> tuple[dict[uuid.UUID, dict[str, int]], PostgresFootprint]:
        """Split the flat PG roll-up into a per-document map AND the collection total (null-doc included)."""
        # 1. Accumulate per document (skipping null doc ids) AND into a collection-wide bucket sum.
        by_doc: dict[uuid.UUID, dict[str, int]] = {}
        totals: dict[str, int] = {}
        for document_id, bucket, size in pg_rows:
            totals[bucket] = totals.get(bucket, 0) + size
            if document_id is not None:
                by_doc.setdefault(document_id, {})[bucket] = (
                    by_doc.setdefault(document_id, {}).get(bucket, 0) + size
                )

        # 2. The collection total folds every bucket — including observability rows with no document.
        return by_doc, StorageFootprintHelpers.postgres_footprint(totals)

    def __collection_meta_carriers(
        self, doc_fields: dict[uuid.UUID, set[str]], profile: QdrantProfile | None
    ) -> dict[str, int]:
        """Sum each semantic field's dense-vector carrier points across the documents that populate it."""
        # A meta vector's collection carrier count is the sum of its carrying documents' point counts.
        meta_points: dict[str, int] = {}
        if profile is None:
            return meta_points
        for document_id, fields in doc_fields.items():
            points = profile.per_document_points.get(str(document_id), 0)
            if not points:
                continue
            for field in fields:
                vector_name = VectorNames.field_dense(field)
                meta_points[vector_name] = meta_points.get(vector_name, 0) + points
        return meta_points

    async def collection_footprint(self, collection_id: uuid.UUID) -> CollectionFootprint:
        """
        Measure a collection's material footprint across S3, Postgres and Qdrant.

        S3 bytes are EXACT (blob registry); Postgres and Qdrant bytes are ESTIMATES (row bytes via
        ``pg_column_size`` / point-count arithmetic). A collection with no documents — or one never
        embedded — reports zeros for the empty stores, never an error.

        Args:
            collection_id (uuid.UUID): The collection to measure.

        Returns:
            CollectionFootprint: Per-store totals + the per-document breakdown (heaviest first).
        """
        # 1. Postgres — the document catalogue, the S3 byte sums (exact) and the row-byte estimate,
        #    all in one short-lived read transaction (three grouped aggregates, no per-row scan).
        async with self._postgres.session() as session:
            names = await StorageFootprintApi.document_names(session, collection_id)
            pg_rows = await StorageFootprintApi.per_document_pg(session, collection_id)
            s3_rows = await StorageFootprintApi.s3_per_document(session, collection_id)
            physical_unique = await StorageFootprintApi.s3_physical_unique(session, collection_id)
            carriers = await StorageFootprintApi.semantic_field_carriers(session, collection_id)

        # 2. Qdrant — profile the vector store once (facet gives per-document counts in one call);
        #    a collection with no space yet profiles as None and contributes zero everywhere.
        name = DatabaseHelpers.qdrant_collection_name(collection_id)
        profile = await QdrantStorageApi.profile(
            self._qdrant.raw, name, facet_limit=max(len(names), 1)
        )

        # 3. Reshape the flat rows into per-document maps + the collection Postgres total.
        s3_by_doc = {
            document_id: (original, rendered) for document_id, original, rendered in s3_rows
        }
        pg_by_doc, postgres_total = self.__collection_postgres(pg_rows)
        doc_fields: dict[uuid.UUID, set[str]] = {}
        for document_id, field_name in carriers:
            doc_fields.setdefault(document_id, set()).add(field_name)

        # 4. Per-document breakdown (sorted), then the S3/Qdrant collection totals. The collection
        #    dense weights content by every point and each meta vector by its own carrier-point sum.
        documents = self.__build_documents(names, pg_by_doc, s3_by_doc, doc_fields, profile)
        s3_total = self.__s3_footprint(
            original=sum(original for _, original, _ in s3_rows),
            rendered=sum(rendered for _, _, rendered in s3_rows),
            physical_unique=physical_unique,
        )
        collection_points = 0 if profile is None else profile.total_points
        collection_carriers = self.__dense_carriers(
            collection_points, self.__collection_meta_carriers(doc_fields, profile)
        )
        qdrant_total = self.__qdrant_footprint(collection_points, collection_carriers, profile)

        # 5. The material footprint uses the DEDUPED S3 disk cost (physical_unique), not the logical sum.
        grand_total = (
            s3_total.physical_unique_bytes + postgres_total.total_bytes + qdrant_total.total_bytes
        )
        self.logger.info(
            f"Storage footprint for collection {collection_id}: "
            f"{len(documents)} docs, grand total {grand_total} bytes"
        )
        return CollectionFootprint(
            collection_id=collection_id,
            s3=s3_total,
            postgres=postgres_total,
            qdrant=qdrant_total,
            grand_total_bytes=grand_total,
            documents=documents,
        )


__all__ = ["StorageFootprintFacade"]
