# ====== Code Summary ======
# CollectionHealthService — the on-demand, ZERO-SPEND operational health of one collection. It builds
# the collection's two graphs (ingest, search) exactly as a real run would (healing + build +
# validate, failures captured not raised), sweeps every provider-hosted leaf for reachability via the
# shared reachability seam (ingest sweep + search sweep — query embedder + reranker), reads the raw
# vector-index size + last successful ingest, and rolls it all up into the operational verdict. It
# writes NOTHING, enqueues NO job, and never runs the engine — the sweep only calls node.preflight().
# ``summarize_structural`` is the fleet-list counterpart: a CHEAP, structural-only roll-up (buildability +
# batched DB counters, NO provider sweep, NO Qdrant round-trip) so rendering the list never probes
# every provider of every collection — the live sweep stays exclusively on the per-collection check().

# ====== Standard Library Imports ======
import uuid
from datetime import UTC, datetime

# ====== Third-Party Library Imports ======
from loggerplusplus import LoggerClass

# ====== Internal Project Imports ======
from shared_libs.pipelines.build import PipelineBuilder
from shared_libs.pipelines.ingest import IngestPipeline
from shared_libs.pipelines.reachability import (
    ProviderEgressPolicy,
    ProviderProbeResult,
    ReachabilitySweep,
    SearchReachabilitySweep,
)
from shared_libs.pipelines.validation import GraphValidator
from shared_libs.services.db import Database
from shared_libs.services.db.postgresql.tables import Collection

# ====== Local Project Imports ======
from .graph_builds import CollectionGraphBuilder, GraphBuildOutcome
from .models import (
    CollectionHealthResponse,
    CollectionHealthSummary,
    CollectionListVerdict,
    IngestHealth,
    SearchHealth,
    SearchIndex,
)
from .verdict import HealthVerdictResolver


class CollectionHealthService(LoggerClass):
    """Composes a collection's operational-health snapshot from build + reachability + index reads."""

    def __init__(
        self,
        database: Database,
        builder: PipelineBuilder,
        validator: GraphValidator,
        egress_policy: ProviderEgressPolicy | None = None,
    ) -> None:
        """
        Args:
            database (Database): The shared data facade (collections, jobs, vector count).
            builder (PipelineBuilder): The shared graph builder (reused, stateless).
            validator (GraphValidator): The shared structural validator (reused, stateless).
            egress_policy (ProviderEgressPolicy | None): The provider egress allowlist gate. When
                set (a non-empty allowlist) a provider whose base_url host is not allowed is reported
                ``blocked`` and NEVER probed — so this READ endpoint cannot be used as a network
                scanner of the internal Docker network. None / empty allowlist → probe as before.
        """
        LoggerClass.__init__(self)
        self._database = database
        self._builder = builder
        self._validator = validator
        self._ingest_sweep = ReachabilitySweep()
        self._search_sweep = SearchReachabilitySweep()
        self._egress_policy = egress_policy

    async def __sweep_ingest(self, ingest: GraphBuildOutcome) -> list[ProviderProbeResult]:
        """Sweep the ingest graph's provider leaves (empty when the graph did not build)."""
        if ingest.group is None:
            return []
        return await self._ingest_sweep.sweep(
            ingest.group, side="ingest", policy=self._egress_policy
        )

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
            return await self._search_sweep.sweep(
                pipeline_blob, search.group, policy=self._egress_policy
            )
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

        # 5. Roll the raw signals up into the headline verdict + reason and the search tri-state.
        rollup = HealthVerdictResolver.overall(
            ingest_buildable=ingest_build.buildable,
            search_buildable=search_build.buildable,
            ingest_providers=ingest_providers,
            search_providers=search_providers,
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
            verdict=rollup.verdict,
            reason=rollup.reason,
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

    def __list_verdict(self, *, ingest_buildable: bool, chunk_count: int) -> CollectionListVerdict:
        """
        Derive the fleet list's LIGHTWEIGHT structural verdict — no provider probe, no Qdrant read.

        Mirrors the structural core of the detail roll-up (`HealthVerdictResolver.overall`) but from
        buildability + a cheap DB count only: a structurally broken ingest blob is ``cannot_ingest``;
        an empty index is the neutral ``empty``; otherwise ``operational``. The network-dependent
        degraded/down states stay EXCLUSIVELY on the on-demand detail probe.

        Args:
            ingest_buildable (bool): Whether the stored ingest blob heals, builds and validates.
            chunk_count (int): The collection's Postgres chunk count.

        Returns:
            CollectionListVerdict: empty / operational / cannot_ingest.
        """
        # 1. A structurally invalid ingest pipeline blocks new ingestion — surface it first.
        if not ingest_buildable:
            return CollectionListVerdict.CANNOT_INGEST
        # 2. Buildable but nothing indexed yet → NEUTRAL empty (ready to ingest).
        if chunk_count == 0:
            return CollectionListVerdict.EMPTY
        # 3. Buildable and populated → operational.
        return CollectionListVerdict.OPERATIONAL

    def summarize_structural(
        self,
        collections: list[Collection],
        *,
        doc_counts: dict[uuid.UUID, int],
        chunk_counts: dict[uuid.UUID, int],
        last_ingests: dict[uuid.UUID, datetime],
    ) -> dict[uuid.UUID, CollectionHealthSummary]:
        """
        Roll up a CHEAP, structural health summary for every fleet collection — the list's single
        server-side source of truth for the dashboard cards.

        PURE (no I/O): it derives a structural verdict from each stored blob's buildability (in-memory
        heal + build + validate) and the caller-supplied BATCHED counters. It deliberately never
        probes a provider nor hits Qdrant (the on-demand detail endpoint owns the live sweep), so
        rendering the list costs three grouped DB queries (fetched by the caller) + a few in-memory
        graph builds — never a per-collection provider stampede. The card thus shows the SAME
        structural determination + the SAME counters as the collection's own overview.

        Args:
            collections (list[Collection]): The already-loaded fleet rows.
            doc_counts (dict[uuid.UUID, int]): Batched document count per collection (0 when absent).
            chunk_counts (dict[uuid.UUID, int]): Batched chunk count per collection (0 when absent).
            last_ingests (dict[uuid.UUID, datetime]): Batched last-successful-ingest per collection.

        Returns:
            dict[uuid.UUID, CollectionHealthSummary]: collection id → its compact health summary.
        """
        # 1. Per collection: a purely structural verdict from the blob's buildability (no I/O) + the
        #    caller's batched counts — never a provider sweep or a Qdrant call.
        summaries: dict[uuid.UUID, CollectionHealthSummary] = {}
        for collection in collections:
            stored_pipeline = collection.pipeline or IngestPipeline.default_blob().model_dump(
                mode="json"
            )
            ingest_build = CollectionGraphBuilder.build_ingest(
                self._builder, self._validator, stored_pipeline
            )
            chunk_count = chunk_counts.get(collection.id, 0)
            summaries[collection.id] = CollectionHealthSummary(
                verdict=self.__list_verdict(
                    ingest_buildable=ingest_build.buildable, chunk_count=chunk_count
                ),
                doc_count=doc_counts.get(collection.id, 0),
                chunk_count=chunk_count,
                last_ingest_at=last_ingests.get(collection.id),
            )
        return summaries


__all__ = ["CollectionHealthService"]
