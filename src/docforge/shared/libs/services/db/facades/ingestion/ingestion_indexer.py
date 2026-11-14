# ====== Code Summary ======
# IngestionIndexer — the vector-indexing half of the ingestion persistence path: ensure the Qdrant
# collection from the metadata schema, refuse points carrying an undeclared vector, upsert the fresh
# points then purge the document's leftover ones (a REPLACE, never an accumulation), flag the chunks
# indexed and advance (or hold) the collection's indexed baseline. Internal collaborator of
# IngestionFacade; callers go through ``Database.ingestion``.

# ====== Standard Library Imports ======
import uuid
from collections.abc import Sequence

# ====== Third-Party Library Imports ======
from loggerplusplus import LoggerClass

# ====== Internal Project Imports ======
from shared_libs.public_models import VectorLayout
from shared_libs.services.db.bricks import VectorSpaceProvisioner
from shared_libs.services.db.index_signature import CollectionIndexSignature
from shared_libs.services.db.postgresql import PostgresClient
from shared_libs.services.db.postgresql.apis import ChunkApi, CollectionApi
from shared_libs.services.db.qdrant import (
    QdrantClient,
    QdrantCollectionApi,
    QdrantIndexApi,
    QdrantPoint,
    VectorNames,
)

# ====== Local Project Imports ======
from ..helpers import DatabaseHelpers
from ..undeclared_vector_error import UndeclaredVectorError


class IngestionIndexer(LoggerClass):
    """Push a document's chunk vectors into Qdrant and keep the indexed baseline honest."""

    def __init__(self, postgres: PostgresClient, qdrant: QdrantClient) -> None:
        LoggerClass.__init__(self)
        self._postgres = postgres
        self._qdrant = qdrant

    async def index(
        self,
        collection_id: uuid.UUID,
        document_id: uuid.UUID,
        dense_dim: int,
        points: Sequence[QdrantPoint],
        layout: VectorLayout | None = None,
    ) -> None:
        """
        Push a document's chunk vectors into Qdrant (replacing its old points) and flag them indexed.

        The Qdrant collection is ensured (lazily created) from the CURRENT metadata schema; a
        dimension change without reindex surfaces as a loud upsert error, never silently. Point ids
        are deterministic per (document, chunk ordinal) (the translator's UUID v5 remap), so the
        fresh points are upserted FIRST — overwriting the previous run's same-ordinal points in place
        — and only THEN are the document's leftover points (ids this run no longer produced: a
        shorter re-chunk, a now-disabled chunk) deleted. A re-ingest is a REPLACE, never an
        accumulation, and a failed upsert leaves the previous points serving instead of none.

        Args:
            collection_id (uuid.UUID): The target collection.
            document_id (uuid.UUID): The document whose points these are — its stale points are
                purged first so a re-ingest never orphans the previous run's vectors.
            dense_dim (int): Dense vector dimension (from the pipeline's embed config).
            points (Sequence[QdrantPoint]): The points (ids = chunk ids) with vectors + payload.
            layout (VectorLayout | None): The embedder's config-derived layout (content axes + sparse
                IDF) — the store schema follows it; None = the legacy dense + sparse, no-IDF layout.
        """
        # 1. Derive the vector space from the schema (and re-check the slug guard defensively).
        async with self._postgres.session() as session:
            schema = await CollectionApi.get_schema(session, collection_id)
        DatabaseHelpers.validate_vector_slugs(schema)
        name = DatabaseHelpers.qdrant_collection_name(collection_id)
        missing_fields = await VectorSpaceProvisioner.ensure(
            self._qdrant.raw, name, schema, dense_dim, layout
        )
        # 2. Refuse points carrying a named vector the store never declared, or a sparse vector the
        #    store declares under another IDF modifier (another encoder's space), before any purge —
        #    a failed re-ingest keeps the document's previous points; Qdrant would 400 on the upsert.
        await self._guard_declared_vectors(collection_id, name, schema, points, layout)
        # 3. Upsert FIRST (deterministic ids overwrite the previous run's points in place), THEN purge
        #    the document's leftover points this run did not produce — otherwise they would survive
        #    as orphans (live document_id + enabled payload → polluting the candidate pool). Never
        #    delete-then-upsert: a failed upsert would leave the document with zero points.
        await QdrantIndexApi.upsert(self._qdrant.raw, name, points)
        await QdrantIndexApi.delete_stale_for_document(
            self._qdrant.raw, name, document_id, [point.point_id for point in points]
        )
        # 4. Flag the chunks as indexed.
        async with self._postgres.session() as session:
            await ChunkApi.mark_indexed(session, [uuid.UUID(point.point_id) for point in points])
        # 5. Advance the indexed baseline: the vectors just landed under the CURRENT config, so stamp
        #    its signature and clear needs_reindex (a real reindex is now the ONLY thing that clears
        #    the flag — the old sticky boolean never did). Best-effort: a failure here must not fail an
        #    ingestion already persisted+upserted (the doc IS indexed; the baseline heals on the next
        #    successful ingest or a config write's derive).
        #    KNOWN LIMITATION: this advances on ANY successful doc ingestion, so a PARTIAL reindex
        #    (only some documents) optimistically clears the flag even if older docs remain on the
        #    previous signature. Acceptable V1 — the documented remediation for a config drift is a
        #    FULL bulk reingest (which DocForge's reindex performs), after which every doc matches.
        #    NEVER advance while the store lacks a semantic/lexical field's named vector: the baseline
        #    would claim the CURRENT schema is indexed although that field is unsearchable (Qdrant
        #    cannot add a vector to a live collection — a reingest never fixes it, an index rebuild does).
        if missing_fields:
            await self._hold_reindex_flag(collection_id, missing_fields)
        else:
            await self._advance_indexed_baseline(collection_id, schema)
        self.logger.info(f"Indexed {len(points)} points into '{name}'")

    async def _guard_declared_vectors(
        self,
        collection_id: uuid.UUID,
        name: str,
        schema: Sequence,
        points: Sequence[QdrantPoint],
        layout: VectorLayout | None = None,
    ) -> None:
        """Fail the ingest clearly when a point carries a vector the store cannot take as is.

        A chunk-scope semantic field made searchable after the collection's first ingest has no named
        vector in the store (Qdrant cannot add one to a live collection), so every upsert would fail
        with Qdrant's opaque "Not existing vector name". The content vectors are always declared by
        ``ensure``; only ``meta_*`` names are checked for declaration, and the store is read only when
        one is carried or a layout is given. With a layout, a carried sparse vector the store declares
        under the other IDF modifier is refused too (writing it would mix two encoders).

        Args:
            collection_id (uuid.UUID): The target collection (named in the rebuild instruction).
            name (str): Its Qdrant collection name.
            schema (Sequence): Its metadata schema (maps a vector name back to its field).
            points (Sequence[QdrantPoint]): The points about to be upserted.
            layout (VectorLayout | None): The embedder's layout (None = no modifier check).

        Raises:
            UndeclaredVectorError: When a carried vector is undeclared or modifier-mismatched.
        """
        # 1. Only metadata vectors can be undeclared — no store read for a content-only legacy ingest.
        carried = {
            vector
            for point in points
            for vector in (*point.dense, *point.sparse)
            if vector.startswith("meta_")
        }
        carried_sparse = {vector for point in points for vector in point.sparse}
        if not carried and (layout is None or not carried_sparse):
            return
        # 2. Compare against the store's declarations; name each offending field.
        declared = await QdrantCollectionApi.declared(self._qdrant.raw, name)
        undeclared = set(carried - declared.dense - declared.sparse)
        if layout is not None:
            undeclared |= carried_sparse & declared.mismatched(layout)
        undeclared = sorted(undeclared)
        if undeclared:
            field_of = {
                vector: field.field_name
                for field in schema
                for vector in (
                    VectorNames.field_dense(field.field_name),
                    VectorNames.field_sparse(field.field_name),
                )
            }
            raise UndeclaredVectorError.for_vectors(collection_id, undeclared, field_of)

    async def _hold_reindex_flag(self, collection_id: uuid.UUID, missing_fields: set[str]) -> None:
        """Keep ``needs_reindex`` raised (baseline untouched) while the store lacks named vectors.

        Best-effort like the baseline advance: a failure here never fails an already-indexed ingest.

        Args:
            collection_id (uuid.UUID): The just-indexed collection.
            missing_fields (set[str]): The semantic/lexical fields whose named vector is undeclared.
        """
        try:
            # 1. Leave indexed_signature as-is and (re)assert the flag — the store is not aligned.
            async with self._postgres.session() as session:
                await CollectionApi.update(session, collection_id, needs_reindex=True)
            self.logger.warning(
                f"Collection {collection_id}: indexed baseline NOT advanced — fields "
                f"{sorted(missing_fields)} have no named vector in the store (index rebuild required)"
            )
        except Exception as exc:  # best-effort: a trailing flag write must never fail an ingest.
            self.logger.warning(f"Could not hold needs_reindex for {collection_id}: {exc}")

    async def _advance_indexed_baseline(self, collection_id: uuid.UUID, schema: Sequence) -> None:
        """Stamp the collection's indexed_signature to the current config and clear needs_reindex.

        Idempotent and best-effort: re-running the same ingest recomputes the same signature, and any
        failure is swallowed so an already-persisted ingestion never fails at this trailing step.

        Args:
            collection_id (uuid.UUID): The just-indexed collection.
            schema (Sequence): The metadata schema the vectors were indexed under (reused from index).
        """
        try:
            # 1. Read the current pipeline blob, compute the signature over (blob + schema), stamp it.
            async with self._postgres.session() as session:
                collection = await CollectionApi.get(session, collection_id)
                if collection is None:
                    return
                signature = CollectionIndexSignature.compute(collection.pipeline, schema)
                await CollectionApi.update(
                    session,
                    collection_id,
                    indexed_signature=signature,
                    indexed_embed_signature=CollectionIndexSignature.embed_signature(
                        collection.pipeline
                    ),
                    needs_reindex=False,
                )
        except (
            Exception
        ) as exc:  # best-effort: a trailing baseline advance must never fail an ingest.
            self.logger.warning(f"Could not advance indexed baseline for {collection_id}: {exc}")


__all__ = ["IngestionIndexer"]
