# ====== Code Summary ======
# CollectionHealthService — the on-demand, ZERO-SPEND operational health of one collection. It builds
# the collection's two graphs (ingest, search) exactly as a real run would (healing + build +
# validate, failures captured not raised), sweeps every provider-hosted leaf for reachability via the
# shared reachability seam (ingest sweep + search sweep — query embedder + reranker), reads the raw
# vector-index size + last successful ingest, and rolls it all up into the operational verdict. It
# writes NOTHING, enqueues NO job, and never runs the engine — the sweep only calls node.preflight().

# ====== Standard Library Imports ======
import uuid
from datetime import UTC, datetime

# ====== Third-Party Library Imports ======
from loggerplusplus import LoggerClass

# ====== Internal Project Imports ======
from shared_libs.pipelines.build import PipelineBuilder
from shared_libs.pipelines.ingest import IngestPipeline
from shared_libs.pipelines.reachability import (
    ProviderProbeResult,
    ReachabilitySweep,
    SearchReachabilitySweep,
)
from shared_libs.pipelines.validation import GraphValidator
from shared_libs.services.db import Database

# ====== Local Project Imports ======
from .graph_builds import CollectionGraphBuilder, GraphBuildOutcome
from .models import (
    CollectionHealthResponse,
    IngestHealth,
    SearchHealth,
    SearchIndex,
)
from .verdict import HealthVerdictResolver


class CollectionHealthService(LoggerClass):
    """Composes a collection's operational-health snapshot from build + reachability + index reads."""

    def __init__(
        self, database: Database, builder: PipelineBuilder, validator: GraphValidator
    ) -> None:
        """
        Args:
            database (Database): The shared data facade (collections, jobs, vector count).
            builder (PipelineBuilder): The shared graph builder (reused, stateless).
            validator (GraphValidator): The shared structural validator (reused, stateless).
        """
        LoggerClass.__init__(self)
        self._database = database
        self._builder = builder
        self._validator = validator
        self._ingest_sweep = ReachabilitySweep()
        self._search_sweep = SearchReachabilitySweep()

    async def __sweep_ingest(self, ingest: GraphBuildOutcome) -> list[ProviderProbeResult]:
        """Sweep the ingest graph's provider leaves (empty when the graph did not build)."""
        if ingest.group is None:
            return []
        return await self._ingest_sweep.sweep(ingest.group, side="ingest")

    async def __sweep_search(
        self, pipeline_blob: dict, search: GraphBuildOutcome
    ) -> list[ProviderProbeResult]:
        """
        Sweep the search graph's providers (query embedder + reranker) when it built.

        The query embedder is rebuilt from the INGEST blob (the shared vector space); a malformed
        embed config there would make the rebuild raise — captured here so a bad blob degrades the
        report rather than 500-ing the endpoint.
        """
        if search.group is None:
            return []
        try:
            return await self._search_sweep.sweep(pipeline_blob, search.group)
        except Exception as exc:  # noqa: BLE001 — a bad embed blob must not crash the probe.
            self.logger.warning(f"Search reachability sweep failed: {type(exc).__name__}: {exc}")
            return []

    async def check(self, collection_id: uuid.UUID) -> CollectionHealthResponse | None:
        """
        Build the full operational-health snapshot for a collection (None when unknown).

        Args:
            collection_id (uuid.UUID): The collection to probe.

        Returns:
            CollectionHealthResponse | None: The snapshot, or None when the collection does not exist.
        """
        # 1. The collection is the source of both blobs — unknown id yields None (router → 404).
        collection = await self._database.collections.get(collection_id)
        if collection is None:
            return None

        # 2. Build both graphs the SAME way a real run does, capturing (not raising) any build error.
        stored_pipeline = collection.pipeline or IngestPipeline.default_blob().model_dump(
            mode="json"
        )
        ingest_build = CollectionGraphBuilder.build_ingest(
            self._builder, self._validator, stored_pipeline
        )
        search_build = CollectionGraphBuilder.build_search(
            self._builder, self._validator, collection.search
        )

        # 3. Reachability — probe every provider leaf of both graphs (outside the nodes; no spend).
        ingest_providers = await self.__sweep_ingest(ingest_build)
        search_providers = await self.__sweep_search(stored_pipeline, search_build)

        # 4. Index facts — raw vector count + the last successful ingest timestamp.
        vector_count = await self._database.collections.vector_count(collection_id)
        last_ingest_at = await self._database.jobs.last_successful_ingest_at(collection_id)

        # 5. Roll the raw signals up into the two headline verdicts.
        verdict = HealthVerdictResolver.overall(
            ingest_buildable=ingest_build.buildable,
            search_buildable=search_build.buildable,
            providers=ingest_providers + search_providers,
            vector_count=vector_count,
        )
        search_operational = HealthVerdictResolver.search(
            search_buildable=search_build.buildable,
            providers=search_providers,
            vector_count=vector_count,
        )

        # 6. Assemble the response contract.
        return CollectionHealthResponse(
            collection_id=str(collection_id),
            verdict=verdict,
            checked_at=datetime.now(UTC),
            ingest=IngestHealth(
                buildable=ingest_build.buildable,
                build_error=ingest_build.error,
                providers=ingest_providers,
            ),
            search=SearchHealth(
                buildable=search_build.buildable,
                search_operational=search_operational,
                build_error=search_build.error,
                providers=search_providers,
                index=SearchIndex(vector_count=vector_count, last_ingest_at=last_ingest_at),
            ),
        )


__all__ = ["CollectionHealthService"]
