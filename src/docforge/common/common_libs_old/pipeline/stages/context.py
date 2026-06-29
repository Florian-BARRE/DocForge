# ====== Code Summary ======
# PipelineContext + StageDeps — the typed, mutable accumulator threaded through the dynamic
# pipeline (Pipeline -> Stage -> Step). Replaces the divergent per-stage run() signatures of
# the legacy orchestrator: every stage reads what it consumes from the context and writes what
# it produces back onto it. StageDeps bundles the shared infrastructure handles (object store,
# Postgres, Qdrant, caches, repositories). ``session`` is intentionally NOT a context key —
# stages open ``deps.postgres.session()`` locally so a session never outlives its stage.
#
# Heavy types are referenced only under TYPE_CHECKING (with ``from __future__ import annotations``
# all field annotations are strings), so this module pulls in no storage/provider code at import
# time and the base contracts can reference PipelineContext without a layer cycle.

# ====== Standard Library Imports ======
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from common_libs.domain.ir.chunk import Chunk
    from common_libs.domain.ir.models import DocumentIR
    from common_libs.pipeline.base.stage.keys import StageKey
    from common_libs.pipeline.caches.node_cache import NodeCache
    from common_libs.pipeline.caches.provider_cache import ProviderCallCache
    from common_libs.pipeline.ingest.stages.enrich.result import EnrichResult
    from common_libs.pipeline.ingest.stages.ingest.result import IngestResult
    from common_libs.pipeline.ingest.stages.parsing.result import ParseResult
    from common_libs.pipeline.stages.s4_chunk.models import S4Result
    from common_libs.pipeline.stages.s5_contextualize.result import S5Result
    from common_libs.pipeline.stages.s5b_metagen.result import S5bResult
    from common_libs.pipeline.stages.s6_embed_index.result import S6Result
    from common_libs.storage.postgres.client import PostgresClient
    from common_libs.storage.postgres.repositories import (
        BlockRepository,
        ChunkRepository,
        DocumentRepository,
    )
    from common_libs.storage.qdrant.client import QdrantStorageClient
    from common_libs.storage.s3.client import S3Client


@dataclass(frozen=True)
class StageDeps:
    """
    Frozen bundle of shared infrastructure handles available to every stage.

    All fields default to ``None`` so a partially-wired context can be constructed in tests;
    in production the assembler injects every handle a stage needs. A stage that requires a
    Postgres session opens ``postgres.session()`` itself — the session is never a context key.

    Attributes:
        s3 (S3Client | None): SeaweedFS S3-compatible object store client.
        postgres (PostgresClient | None): Postgres session factory.
        qdrant (QdrantStorageClient | None): Qdrant vector store client.
        node_cache (NodeCache | None): Merkle-DAG node cache (stage_run table).
        provider_cache (ProviderCallCache | None): Cross-document provider-call cache.
        document_repo (DocumentRepository | None): Document status / metadata operations.
        block_repo (BlockRepository | None): IR block persistence operations.
        chunk_repo (ChunkRepository | None): Chunk persistence operations.
    """

    s3: "S3Client | None" = None
    postgres: "PostgresClient | None" = None
    qdrant: "QdrantStorageClient | None" = None
    node_cache: "NodeCache | None" = None
    provider_cache: "ProviderCallCache | None" = None
    document_repo: "DocumentRepository | None" = None
    block_repo: "BlockRepository | None" = None
    chunk_repo: "ChunkRepository | None" = None


@dataclass
class PipelineContext:
    """
    Mutable typed accumulator threaded through a full pipeline run.

    Each stage reads the keys it declares in ``CONSUMES`` and writes the keys it declares in
    ``PRODUCES``. ``fingerprints`` / ``from_cache`` carry per-stage cache bookkeeping; ``aux``
    is a free-form scratch space (it also holds the run's ``ExecutionTrace`` under
    ``aux["execution_trace"]``).

    Attributes:
        deps (StageDeps | None): Shared infrastructure handles for the run.
        doc_id (str | uuid.UUID | None): Document primary key.
        source_hash (str | None): SHA-256 content address of the original file.
        filename (str | None): Original filename.
        file_bytes (bytes | None): Raw original bytes (downloaded from S3 when absent).
        collection_id (str | None): Target Qdrant collection name, or None (no indexing).
        metadata_fields (list[Any] | None): Per-collection metadata field specs.
        doc_user_meta (dict[str, Any] | None): User-supplied business metadata at ingest.
        ingest_result (IngestResult | None): Ingest stage output.
        parse_result (ParseResult | None): Parse stage output.
        ir (DocumentIR | None): The canonical IR (set by parse, mutated by enrich).
        enrich_result (EnrichResult | None): Enrich (S2) output.
        chunks (list[Chunk] | None): The current chunk set (chunk -> contextualize -> metagen).
        doc_fields (dict[str, Any]): Document-scope generated values from metagen.
        doc_meta (dict[str, Any]): Assembled document-level metadata fed to embed/index.
        chunk_result (S4Result | None): S4 (chunk) output.
        contextualize_result (S5Result | None): S5 (contextualize) output.
        metagen_result (S5bResult | None): S5b (metagen) output.
        embed_result (S6Result | None): S6 (embed + index) output.
        fingerprints (dict[str, str]): Per-stage Merkle fingerprints (cache keys).
        from_cache (dict[str, bool]): Per-stage cache-hit flags.
        aux (dict[str, Any]): Free-form scratch space (holds the ExecutionTrace).
    """

    deps: "StageDeps | None" = None
    # ─── Run inputs (the externally-provided roots) ───
    doc_id: "str | uuid.UUID | None" = None
    source_hash: str | None = None
    filename: str | None = None
    original_bytes: bytes | None = None
    collection_id: str | None = None
    metadata_fields: "list[Any] | None" = None
    doc_user_meta: "dict[str, Any] | None" = None
    # ─── Per-stage domain outputs (named by the stage that produces them) ───
    ingest_result: "IngestResult | None" = None
    parse_result: "ParseResult | None" = None
    ir: "DocumentIR | None" = None
    enrich_result: "EnrichResult | None" = None
    chunks: "list[Chunk] | None" = None
    doc_fields: dict[str, Any] = field(default_factory=dict)
    doc_meta: dict[str, Any] = field(default_factory=dict)
    chunk_result: "S4Result | None" = None
    contextualize_result: "S5Result | None" = None
    metagen_result: "S5bResult | None" = None
    embed_result: "S6Result | None" = None
    # ─── Per-stage cache bookkeeping (keyed by the canonical StageKey) ───
    fingerprints: "dict[StageKey, str]" = field(default_factory=dict)
    from_cache: "dict[StageKey, bool]" = field(default_factory=dict)
    aux: dict[str, Any] = field(default_factory=dict)


__all__ = ["PipelineContext", "StageDeps"]
