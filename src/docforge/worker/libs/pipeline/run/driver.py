# ====== Code Summary ======
# IngestRunner — the per-job driver that runs one document through the flow ingest pipeline. Given a
# job (the document identity + the collection's stored PipelineConfig + metadata schema) it builds the
# live flow pipeline + service registry via the FlowPipelineBuilder, constructs a FRESH per-run
# WorkerEngineHooks, runs the FlowEngine, and assembles the IngestRunResult the arq task reads. The
# infra (clients + repos + caches) is wired once at worker bootstrap and reused across jobs; only the
# hooks + pipeline are per-run.

# ====== Standard Library Imports ======
import uuid
from typing import Any

# ====== Third-Party Library Imports ======
from loggerplusplus import LoggerClass

# ====== Internal Project Imports ======
from common_libs.pipelines.build import FlowPipelineBuilder
from common_libs.pipelines.builder import IngestClients
from common_libs.pipelines.flow import FlowEngine, RunContext
from common_libs.pipelines.run_input import IngestRunInput

# ====== Local Project Imports ======
from .deps import IngestInfra
from .hooks import WorkerEngineHooks
from .result import IngestRunResult


class IngestRunner(LoggerClass):
    """
    Drives one ingest job on the flow engine (build -> run with the worker hooks -> assemble result).

    Built once at worker bootstrap with the long-lived infra; ``run`` is called per job. The pipeline
    is rebuilt fresh per run from the stable stored config (it carries live handles), and a fresh
    WorkerEngineHooks instance carries the per-run lifecycle + cache state.
    """

    def __init__(
        self,
        *,
        object_store: Any,
        converter: Any,
        postgres: Any,
        qdrant: Any,
        node_cache: Any,
        provider_cache: Any,
        serializer: Any,
        document_repo: Any,
        block_repo: Any,
        chunk_repo: Any,
        defaults_cfg: Any = None,
    ) -> None:
        """
        Args:
            object_store / converter / postgres / qdrant / provider_cache / serializer: The live infra
                handles the builder registers as pipeline services.
            node_cache / document_repo / block_repo / chunk_repo: The infra the lifecycle hooks consume.
            defaults_cfg (Any): Deployment config supplying env-level provider defaults (GPU flags…).
        """
        LoggerClass.__init__(self)
        # Clients the builder registers as pipeline services.
        self._clients = IngestClients(
            object_store=object_store,
            converter=converter,
            qdrant=qdrant,
            postgres=postgres,
            serializer=serializer,
            provider_cache=provider_cache,
        )
        # The subset the run-time hooks need (status / IR / node-cache / chunk fallback).
        self._infra = IngestInfra(
            object_store=object_store,
            postgres=postgres,
            node_cache=node_cache,
            document_repo=document_repo,
            block_repo=block_repo,
            chunk_repo=chunk_repo,
        )
        self._builder = FlowPipelineBuilder(defaults_cfg)

    async def run(
        self,
        *,
        doc_id: uuid.UUID,
        source_hash: str,
        filename: str,
        original_bytes: bytes,
        pipeline_config: Any,
        metadata_fields: list | None = None,
        collection_id: str | None = None,
        doc_user_meta: dict | None = None,
    ) -> IngestRunResult:
        """
        Run one document through the ingest pipeline and return the aggregated result.

        Args:
            doc_id (uuid.UUID): The document id (status target + node-cache row key).
            source_hash (str): The original's content address (S3 keys for download + codec).
            filename (str): The original filename.
            original_bytes (bytes): The raw original bytes (empty -> the hooks re-download by hash).
            pipeline_config (Any): The collection's stored PipelineConfig.
            metadata_fields (list | None): The collection metadata schema (feeds metagen / embed).
            collection_id (str | None): Target collection (None -> no indexing; embed/index gated off).
            doc_user_meta (dict | None): Caller-supplied per-document business metadata.

        Returns:
            IngestRunResult: Status + per-stage fingerprints + cache flags + chunk/embed tallies.
        """
        # 1. Build the live pipeline + its service registry from the stored config.
        pipeline, registry = self._builder.build(pipeline_config, self._clients, metadata_fields)

        # 2. Fresh per-run hooks (lifecycle + cache state) and run input.
        hooks = WorkerEngineHooks(self._infra, doc_id, source_hash)
        run = RunContext(
            run_input=IngestRunInput(
                original_bytes=original_bytes,
                filename=filename,
                doc_id=str(doc_id),
                collection_id=collection_id,
                metadata_fields=metadata_fields,
                doc_user_meta=doc_user_meta,
            ),
            services=registry,
        )

        # 3. Run the engine with the worker lifecycle hooks, then assemble the result.
        _output, report = await FlowEngine(hooks).run(pipeline, run)
        self.logger.info(f"Ingest run for doc_id={doc_id} finished: status={report.status}.")
        return self._build_result(report, hooks)

    @staticmethod
    def _build_result(report: Any, hooks: WorkerEngineHooks) -> IngestRunResult:
        """
        Assemble the IngestRunResult from the run report + the per-run hooks accumulators.

        Args:
            report (Any): The root NodeReport (status).
            hooks (WorkerEngineHooks): The per-run hooks (fingerprints, cache flags, stage outputs).

        Returns:
            IngestRunResult: The job summary.
        """
        # 1. Pull the chunk / embed tallies off the captured stage outputs (absent -> None).
        outputs = hooks.stage_outputs
        chunk_output = outputs.get("chunk")
        embed_output = outputs.get("embed_index")
        return IngestRunResult(
            status=str(report.status),
            stage_fingerprints=hooks.fingerprints,
            from_cache=hooks.from_cache,
            chunk_result=getattr(chunk_output, "chunk_result", None),
            embed_result=getattr(embed_output, "embed_result", None),
            stage_outputs=outputs,
        )


__all__ = ["IngestRunner"]
