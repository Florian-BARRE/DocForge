# ====== Code Summary ======
# CostEstimateService — the thin edge that turns a collection id + request into a pre-hoc cost/volume
# estimate. It gathers the impure inputs (the collection's ACTUAL pipeline config healed to a
# PipelineState, its contract's generated-field counts, its per-collection estimate overrides, and
# cheap per-document stats over the requested scope/subset), then hands them to the PURE estimator.
# The estimator does the arithmetic; this service only reads (no writes, no spend). It selects the
# covered documents three ways — a whole-collection scope, an explicit id subset, or a corpus filter
# (reusing the document-grid resolver) — and folds any per-collection overrides over the global rate
# table + assumptions. An unreadable stored blob raises BlobNormalizationError (422); an unknown
# collection returns None (404); a bad id/filter surfaces as ValueError (422).

# ====== Standard Library Imports ======
import uuid

# ====== Third-Party Library Imports ======
from loggerplusplus import LoggerClass

# ====== Internal Project Imports ======
from config import RUNTIME_CONFIG
from shared_libs.pipelines.build.blob import GroupNodeBlob
from shared_libs.pipelines.ingest import BlobNormalizer
from shared_libs.pipelines.ingest.estimate import (
    CostEstimate,
    CostEstimator,
    CostPlanExtractor,
)
from shared_libs.pipelines.ingest.stages import StateReader
from shared_libs.public_models import FieldOrigin, FieldScope
from shared_libs.services.db import Database
from shared_libs.services.db.postgresql.tables import (
    Document,
    DocumentStatus,
    MetadataField,
)

# ====== Local Project Imports ======
from ...libs.corpus import DocumentSelector, DocumentSelectorResolver
from .errors import EstimateInputError
from .merger import EstimateOverrideMerger
from .models import CollectionEstimateRequest
from .overrides import EstimateOverrides
from .sampler import DocumentSampler


class CostEstimateService(LoggerClass):
    """Gathers a collection's config + document stats and runs the pure cost estimator."""

    def __init__(self, database: Database) -> None:
        """Store the database façade — the only impure dependency (reads only)."""
        LoggerClass.__init__(self)
        self._database = database
        # A filter/id subset matching MORE than this samples the first N rows and scales the estimate
        # linearly (via the sampler's document_count seam) — so a 100k-doc estimate never fetches 100k.
        self._sample_cap = RUNTIME_CONFIG.ESTIMATE_MAX_SAMPLE_DOCUMENTS

    async def estimate(
        self, collection_id: uuid.UUID, request: CollectionEstimateRequest
    ) -> CostEstimate | None:
        """
        Project the cost and volume of ingesting the requested documents WITHOUT running anything.

        Args:
            collection_id (uuid.UUID): The collection to estimate.
            request (CollectionEstimateRequest): Which documents to cover (scope / ids / filter).

        Returns:
            CostEstimate | None: The estimate, or None when the collection does not exist.

        Raises:
            BlobNormalizationError: The stored pipeline blob cannot be read (surfaced as 422).
            EstimateInputError: A bad document id or corpus filter (surfaced as 422). Narrow on
                purpose — an unrelated ValueError from the pure estimator's arithmetic is NOT caught
                here, so it surfaces as a 500 (a real bug) rather than being masked as a client 422.
        """
        # 1. Resolve the collection (None ⇒ 404 upstream).
        collection = await self._database.collections.get(collection_id)
        if collection is None:
            return None

        # 2. Heal the stored blob to the canonical PipelineState — the ACTUAL pipeline config.
        state = StateReader.read(
            GroupNodeBlob.model_validate(BlobNormalizer.normalize(collection.pipeline))
        )

        # 3. Count the contract's generated fields (metagen fans out over them).
        schema = await self._database.collections.get_schema(collection_id)
        chunk_fields, document_fields = self.__count_generated_fields(schema)

        # 4. Fold the collection's partial overrides over the global rate table + assumptions; the
        #    chunker config still wins for chunk sizing (inside merged_assumptions).
        overrides = self.__overrides(collection)
        assumptions = EstimateOverrideMerger.merged_assumptions(overrides, state.chunker_config)
        rates = EstimateOverrideMerger.merged_rates(overrides)
        plan = CostPlanExtractor.extract(state, chunk_fields, document_fields)

        # 5. Select + measure the covered documents, then run the pure estimator.
        documents, document_count = await self.__select_documents(collection_id, request, schema)
        stats = DocumentSampler.aggregate(documents, assumptions, document_count=document_count)
        return CostEstimator.estimate(plan, stats, rates, assumptions)

    @staticmethod
    def __overrides(collection: object) -> EstimateOverrides | None:
        """Validate the stored partial overrides to the typed model (None when unset)."""
        stored = getattr(collection, "estimate_overrides", None)
        return EstimateOverrides.model_validate(stored) if stored else None

    async def __select_documents(
        self,
        collection_id: uuid.UUID,
        request: CollectionEstimateRequest,
        schema: list[MetadataField],
    ) -> tuple[list[Document], int]:
        """
        Select the documents the estimate covers and how many it represents.

        Returns:
            tuple[list[Document], int]: the measured rows, and the TOTAL covered count. When the
                total exceeds the sample cap only the first N rows are measured and the count drives
                the estimator's linear scaling.
        """
        # 1. An explicit subset (ids or corpus filter) → reuse the shared corpus resolver (validates
        #    existence + collection ownership + filter fields; raises ValueError → 422).
        selector = self.__selector(request)
        if selector is not None:
            try:
                matched = await DocumentSelectorResolver(self._database).resolve(
                    collection_id, selector, schema
                )
            except ValueError as exc:
                # A bad id/filter is the CALLER's fault → a typed 422, never a masked-away 500.
                raise EstimateInputError(str(exc)) from exc
            sample = matched[: self._sample_cap]
            documents = await self._database.documents.get_by_ids(sample)
            return documents, len(matched)

        # 2. No subset → the whole collection, narrowed by scope (pending = not-yet-ingested).
        #    Bounded like the subset path: count the covered set cheaply, then measure only the first
        #    N rows and let the estimator scale linearly (document_count seam) — so a 100k-doc scope
        #    never loads 100k Document rows into memory.
        status = DocumentStatus.PENDING if request.scope == "pending" else None
        document_count = await self._database.documents.count_for_collection(collection_id, status)
        documents = await self._database.documents.list_for_collection(
            collection_id, status=status, limit=self._sample_cap
        )
        return documents, document_count

    @staticmethod
    def __selector(request: CollectionEstimateRequest) -> DocumentSelector | None:
        """Build the shared DocumentSelector for a subset request (None ⇒ whole-collection scope)."""
        # 1. Explicit ids — a non-UUID string is a CALLER fault, surfaced as a typed 422.
        if request.document_ids is not None:
            try:
                return DocumentSelector(
                    document_ids=[uuid.UUID(value) for value in request.document_ids]
                )
            except ValueError as exc:
                raise EstimateInputError(f"document_ids: not a UUID ({exc}).") from exc
        # 2. Corpus filter — the grid's exact filter shape, resolved to matching ids downstream.
        if request.filter is not None:
            return DocumentSelector(filter=request.filter)
        # 3. Neither → no selector; the caller falls back to whole-collection scope.
        return None

    @staticmethod
    def __count_generated_fields(schema: list[MetadataField]) -> tuple[int, int]:
        """Count generated metadata fields split by scope (chunk, document)."""
        chunk = sum(
            1 for f in schema if f.origin == FieldOrigin.GENERATED and f.scope == FieldScope.CHUNK
        )
        document = sum(
            1
            for f in schema
            if f.origin == FieldOrigin.GENERATED and f.scope == FieldScope.DOCUMENT
        )
        return chunk, document


__all__ = ["CostEstimateService"]
