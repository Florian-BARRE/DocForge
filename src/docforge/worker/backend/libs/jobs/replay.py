# ====== Code Summary ======
# ReplayRun — the worker's replay-from-stage mode of an ingest job (job.replay_from set). Instead of
# running the whole graph on the uploaded bytes, it plans the replay on the built graph (pure
# ReplayPlanner), rebuilds the upstream artefacts from the PERSISTED state (ReplaySourceFacade — the IR,
# the stored chunks, the generated document metadata), seeds the engine with them (ReplaySeeder →
# ResumePoint) and runs ONLY the downstream subgraph: no intake, no parse. The delivery is translated
# by the same RunTranslator and persisted downstream-only (ReplayPersistFacade — blocks/pages/blobs are
# never touched), then indexed through the shared DocumentIndexer. Errors propagate to ingest_document's
# handlers: the JOB goes FAILED (breadcrumb + partial trace) or CANCELLED like a full run, but the
# DOCUMENT keeps its prior status with a warning — its previous chunks/points are untouched and served.

# ====== Standard Library Imports ======
from datetime import UTC, datetime
from typing import Any

# ====== Internal Project Imports (worker) ======
from backend.context import CONTEXT

# ====== Internal Project Imports ======
from shared_libs.pipelines.build import PipelineBuilder
from shared_libs.pipelines.ingest.replay import (
    PersistedArtifacts,
    ReplayPlanner,
    ReplaySeeder,
    ReplayUnsupportedError,
    SeedKind,
)
from shared_libs.pipelines.ingest.stages import StageKey
from shared_libs.public_models import GeneratedDocumentMeta

# ====== Local Project Imports ======
from .ingest import IngestServices, Persister, ReplayInputs, RunExecutor
from .stage_plan import StagePlanHelpers

_ZERO_CHUNK_WARNING = (
    "Replay completed but produced 0 chunks — nothing retrievable was created "
    "(the document may be empty or image-only with no extractable text)."
)


class ReplayRun:
    """Static-only: execute one replay-from-stage ingest job end to end."""

    def __new__(cls, *args: object, **kwargs: object) -> None:
        raise TypeError("ReplayRun is a static-only class and cannot be instantiated.")

    @staticmethod
    async def __persisted(
        database: Any, document: Any, needs: set[SeedKind], crops: bool
    ) -> PersistedArtifacts:
        """Load only the persisted artefacts the plan reads."""
        ir = await database.replay_source.load_ir(document.id, with_crops=crops)
        if ir is None:
            raise RuntimeError(f"document {document.id} has no persisted IR to replay from")
        chunks = (
            await database.replay_source.load_chunks(document.id)
            if SeedKind.CHUNKS in needs
            else []
        )
        meta = (
            await database.replay_source.load_document_meta(document.id)
            if SeedKind.DOCUMENT_META in needs
            else GeneratedDocumentMeta()
        )
        ingest = database.replay_source.ingest_facts(document)
        return PersistedArtifacts(ingest=ingest, ir=ir, chunks=chunks, document_meta=meta)

    @classmethod
    async def execute(cls, inputs: ReplayInputs) -> None:
        """
        Plan → seed → run downstream → translate → persist downstream-only → index → DONE.

        Args:
            inputs (ReplayInputs): The rehydrated job inputs.

        Raises:
            RuntimeError: The pipeline can no longer replay this stage (it changed since admission)
                or the document has no persisted IR.
            PipelineRunError: The downstream run failed (carries breadcrumb + partial record).
        """
        services = IngestServices.from_context(CONTEXT)
        database = services.database
        executor = RunExecutor(services, cache_hook_factory=None)
        persister = Persister(services)
        document, blob = inputs.document, inputs.blob

        # 1. Plan on the built graph (pure); a pipeline edited since admission may refuse now.
        group = PipelineBuilder().build(blob)
        try:
            plan = ReplayPlanner.plan(group, inputs.stage)
        except ReplayUnsupportedError as exc:
            raise RuntimeError(
                f"replay from '{inputs.stage}' is no longer possible: {exc}"
            ) from exc

        # 2. Rebuild the seeds from the persisted state and build the engine's resume point.
        needs = {need.kind for need in plan.needs}
        persisted = await cls.__persisted(database, document, needs, plan.needs_crops)
        resume = ReplaySeeder.resume_point(plan, group, persisted)

        # 3. Live progress over the DOWNSTREAM stages only (the percentage counts what runs).
        planned = [
            node_id
            for node_id in StagePlanHelpers.planned_stage_ids(blob)
            if node_id in plan.downstream_ids
        ]
        guarded = RunExecutor.guarded_progress(inputs.job_id, blob, inputs.collection, planned)

        # 4. Run ONLY the downstream subgraph on the seeds (no cache: parse never runs).
        bundle, record = await executor.run_replay(
            blob,
            inputs.source,
            inputs.contract,
            timeout_seconds=inputs.timeout_seconds,
            progress_callback=guarded,
            trace_level=inputs.trace_level,
            resume=resume,
        )

        # 5. The (downstream-only) execution tree onto the job timeline.
        await persister.persist_execution_tree(inputs.job_id, record, inputs.trace_level)

        # 6. Translate with the SAME translator, persist only the downstream layers, then index.
        translated = persister.translate(document.id, bundle, inputs.schema, blob)
        await persister.save_downstream(
            document.id,
            translated,
            replace_enrichments=plan.stage is StageKey.ENRICH,
            replace_document_meta=bundle.document_meta is not None,
            warning_reason=None if bundle.chunks else _ZERO_CHUNK_WARNING,
        )
        await persister.index(document.collection_id, document.id, translated)
        await database.jobs.mark_done(inputs.job_id, finished_at=datetime.now(UTC))
        services.logger.info(
            f"Replay from '{inputs.stage}' done for document {document.id}: "
            f"{len(bundle.chunks)} chunk(s), start node '{plan.start_node_id}'"
        )


__all__ = ["ReplayInputs", "ReplayRun"]
