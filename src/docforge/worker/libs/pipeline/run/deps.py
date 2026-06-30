# ====== Code Summary ======
# IngestInfra — the frozen bundle of worker-owned infrastructure the run-time EngineHooks need to
# reproduce the ingest lifecycle (document status transitions, IR-block persistence, node-cache
# read/write, the PG-only chunk fallback). It is the SUBSET of the worker's injected infra the hooks
# touch; the heavier collaborators only the builder needs (Qdrant, the provider-call cache, the
# converter, the serializer) stay on the IngestRunner, never on the hooks.

# ====== Standard Library Imports ======
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class IngestInfra:
    """
    Frozen container of the infrastructure the run-time hooks consume.

    Built once by ``IngestRunner`` and handed to every per-run ``WorkerEngineHooks`` instance, so the
    individual hook methods never accept these as repeated keyword arguments.

    Attributes:
        object_store (Any): S3Client (SeaweedFS) — original download + cached-artefact codec I/O.
        postgres (Any): PostgresClient — session factory for every status / block / chunk write.
        node_cache (Any): NodeCache — Merkle node-cache (stage_run table) for the NODE_CACHED stages.
        document_repo (Any): DocumentRepository — document status + implicit_meta transitions.
        block_repo (Any): BlockRepository — IR-block persistence after the enrich stage.
        chunk_repo (Any): ChunkRepository | None — the Postgres-only chunk fallback when embed/index
            is gated off (no collection); None when chunk persistence is disabled.
    """

    object_store: Any
    postgres: Any
    node_cache: Any
    document_repo: Any
    block_repo: Any
    chunk_repo: Any


__all__ = ["IngestInfra"]
