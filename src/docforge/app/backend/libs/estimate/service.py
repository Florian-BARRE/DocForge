# ====== Code Summary ======
# CostEstimateService — the thin edge that turns a collection id into a pre-hoc cost/volume estimate.
# It gathers the impure inputs (the collection's ACTUAL pipeline config healed to a PipelineState, its
# contract's generated-field counts, and cheap per-document stats), then hands them to the PURE
# estimator. The estimator does the arithmetic; this service only reads (no writes, no spend). An
# unreadable stored blob raises BlobNormalizationError for the router to surface as a 422; an unknown
# collection returns None for a 404.

# ====== Standard Library Imports ======
import uuid

# ====== Third-Party Library Imports ======
from loggerplusplus import LoggerClass

# ====== Internal Project Imports ======
from shared_libs.pipelines.build.blob import GroupNodeBlob
from shared_libs.pipelines.ingest import BlobNormalizer
from shared_libs.pipelines.ingest.estimate import (
    CostEstimate,
    CostEstimator,
    CostPlanExtractor,
    EstimateAssumptions,
    RateTable,
)
from shared_libs.pipelines.ingest.stages import StateReader
from shared_libs.public_models import FieldOrigin, FieldScope
from shared_libs.services.db import Database
from shared_libs.services.db.postgresql.tables import DocumentStatus, MetadataField

# ====== Local Project Imports ======
from .sampler import DocumentSampler


class CostEstimateService(LoggerClass):
    """Gathers a collection's config + document stats and runs the pure cost estimator."""

    def __init__(self, database: Database) -> None:
        """Store the database façade — the only impure dependency (reads only)."""
        LoggerClass.__init__(self)
        self._database = database

    async def estimate(self, collection_id: uuid.UUID, scope: str) -> CostEstimate | None:
        """
        Project the cost and volume of ingesting a collection's documents WITHOUT running anything.

        Args:
            collection_id (uuid.UUID): The collection to estimate.
            scope (str): ``pending`` (uploaded-but-not-ingested) or ``all`` documents.

        Returns:
            CostEstimate | None: The estimate, or None when the collection does not exist.

        Raises:
            BlobNormalizationError: The stored pipeline blob cannot be read (surfaced as 422).
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

        # 4. Assemble the plan (which stages spend) and the assumptions (chunk sizing from config).
        assumptions = self.__assumptions(state.chunker_config)
        plan = CostPlanExtractor.extract(state, chunk_fields, document_fields)

        # 5. Gather cheap per-document stats over the requested scope, then run the pure estimator.
        documents = await self._database.documents.list_for_collection(collection_id)
        if scope == "pending":
            documents = [d for d in documents if d.status == DocumentStatus.PENDING]
        stats = DocumentSampler.aggregate(documents, assumptions)
        return CostEstimator.estimate(plan, stats, RateTable.default(), assumptions)

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

    @staticmethod
    def __assumptions(chunker_config: dict) -> EstimateAssumptions:
        """Build the assumptions, taking chunk sizing from the collection's chunker config."""
        # target_tokens (structure_aware/semantic) or max_tokens (fixed_size); default 512.
        target = int(chunker_config.get("target_tokens") or chunker_config.get("max_tokens") or 512)
        overlap = int(chunker_config.get("overlap_tokens") or 0)
        return EstimateAssumptions(
            target_chunk_tokens=target,
            chunk_overlap_ratio=(overlap / target if target else 0.0),
        )


__all__ = ["CostEstimateService"]
