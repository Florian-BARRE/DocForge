# ====== Code Summary ======
# WorkerEngineHooks — the concrete EngineHooks the worker injects into the node-engine PipelineEngine
# to reproduce the ingest lifecycle. A FRESH instance is built per job (the IngestRunner makes one):
# it holds the injected infra + the per-run accumulators (stage fingerprints, cache-hit flags, the
# captured stage outputs). Every per-node hook receives the node's resolved ``ctx``. The hooks:
#   - prepare: ensure the original bytes are available (download from S3 when the run input lacks them).
#   - before_node: flip the document 'processing' (ingest) + record a NODE_CACHED 'running' row.
#   - cache_load / cache_store: compute + record the NODE_CACHED stage fingerprint, read/write the node
#     cache, and (de)serialise the stage output to S3 via the codec.
#   - should_run / on_skipped: the collection gate (embed/index runs only with a collection, else the
#     chunks are persisted to Postgres only).
#   - after_node: persist IR blocks + 'parsed' after enrich; flush embed traces after embed/index.
#   - on_error / mark_failed / mark_done: NODE_CACHED 'failed' + terminal document status.

# ====== Standard Library Imports ======
import uuid

# ====== Third-Party Library Imports ======
from loggerplusplus import LoggerClass

# ====== Internal Project Imports ======
from common_libs.pipelines import (
    AbstractNode,
    CachePolicy,
    ContextBase,
    NodeKind,
    NodeOutput,
    RunContext,
)
from common_libs.pipelines.engine import EngineHooks
from common_libs.storage.s3.helpers import S3Helpers

# ====== Local Project Imports ======
from .codec import StageOutputCodec
from .deps import IngestInfra
from .fingerprint import NodeFingerprintHelpers
from .persist import IngestPersistHelpers

# The three NODE_CACHED ingest stages — the only nodes whose fingerprint + S3 codec the hooks manage.
_NODE_CACHED_STAGES: frozenset[str] = frozenset({"ingest", "parse", "enrich"})


class WorkerEngineHooks(EngineHooks, LoggerClass):
    """
    Per-run worker EngineHooks reproducing the ingest lifecycle on the node-engine PipelineEngine.

    Construct ONE per job: it accumulates each NODE_CACHED stage's Merkle fingerprint (so a downstream
    stage folds its upstream fingerprints), the per-stage cache-hit flags, and the captured stage
    outputs (read by the IngestRunner to assemble the EngineResult). All I/O is delegated to the
    codec / fingerprint / persist helpers.
    """

    def __init__(self, infra: IngestInfra, doc_id: uuid.UUID, source_hash: str) -> None:
        """
        Args:
            infra (IngestInfra): The injected worker infra (S3, Postgres, node cache, repos).
            doc_id (uuid.UUID): The document id (the node-cache row key + status target).
            source_hash (str): The original's content address (original download + codec S3 keys).
        """
        LoggerClass.__init__(self)
        self._infra = infra
        self._doc_id = doc_id
        self._source_hash = source_hash
        # Per-run accumulators — fresh per instance, never shared across jobs.
        self._fingerprints: dict[str, str] = {}
        self._from_cache: dict[str, bool] = {}
        self._stage_outputs: dict[str, NodeOutput] = {}

    @property
    def fingerprints(self) -> dict[str, str]:
        """The accumulated NODE_CACHED stage fingerprints (keyed by stage key)."""
        return self._fingerprints

    @property
    def from_cache(self) -> dict[str, bool]:
        """The per-NODE_CACHED-stage cache-hit flags (keyed by stage key)."""
        return self._from_cache

    @property
    def stage_outputs(self) -> dict[str, NodeOutput]:
        """The captured per-stage outputs (run + cache-hit), keyed by stage key."""
        return self._stage_outputs

    async def prepare(self, run: RunContext) -> None:
        """Ensure the original bytes are on the run input (download from S3 when absent). Fail-closed."""
        # 1. The run input already carries the bytes (the common upload path) — nothing to do.
        if run.run_input.original_bytes:
            return
        # 2. Re-ingestion path: download the original by content address and rebuild the (frozen)
        #    run input so the content-address step sees the real bytes (not an empty sentinel).
        try:
            data = await self._infra.object_store.download(S3Helpers.key_original(self._source_hash))
            run.run_input = run.run_input.model_copy(update={"original_bytes": data})
        except Exception as exc:
            self.logger.error(
                f"Original download failed for doc_id={self._doc_id} "
                f"({type(exc).__name__}: {exc}) - marking document 'failed'."
            )
            await IngestPersistHelpers.mark_failed(self._infra, self._doc_id)
            raise

    async def should_run(self, node: AbstractNode, ctx: ContextBase, run: RunContext) -> bool:
        """Gate the embed/index stage on a collection being set; every other node always runs."""
        if node.KIND == NodeKind.STAGE and node.key == "embed_index":
            return run.run_input.collection_id is not None
        return True

    async def on_skipped(self, node: AbstractNode, ctx: ContextBase, run: RunContext) -> None:
        """When embed/index is skipped (no collection), persist the chunks to Postgres only."""
        if not (node.KIND == NodeKind.STAGE and node.key == "embed_index"):
            return
        chunks = list(getattr(ctx.input, "chunks", []) or [])
        if self._infra.chunk_repo is None or not chunks:
            return
        async with self._infra.postgres.session() as session:
            await self._infra.chunk_repo.bulk_insert(session, chunks)
        self.logger.info(f"embed/index skipped (no collection): persisted {len(chunks)} chunks to PG.")

    async def before_node(self, node: AbstractNode, ctx: ContextBase, run: RunContext) -> None:
        """Flip 'processing' as ingest begins and record a NODE_CACHED 'running' stage_run row."""
        if node.KIND != NodeKind.STAGE:
            return
        # 1. The document enters 'processing' as the first stage (ingest) begins.
        if node.key == "ingest":
            async with self._infra.postgres.session() as session:
                await self._infra.document_repo.update_status(session, self._doc_id, "processing")
        # 2. A NODE_CACHED stage records a 'running' row (only reached on a cache miss — the engine
        #    skips before_node on a hit, so the marker never clobbers a cached 'done' row).
        if node.key in _NODE_CACHED_STAGES:
            await self._infra.node_cache.start(self._doc_id, node.key, self._fingerprints[node.key])

    async def cache_load(
        self, node: AbstractNode, ctx: ContextBase, run: RunContext
    ) -> NodeOutput | None:
        """Compute + record the stage fingerprint, then read the node cache (decoding on a hit)."""
        # 1. Compute and ACCUMULATE the fingerprint (hit or miss) so downstream stages fold it.
        fingerprint = NodeFingerprintHelpers.compute(node, run.services, self._fingerprints)
        self._fingerprints[node.key] = fingerprint

        # 2. Consult the node cache; a miss returns None (the engine then runs the stage).
        output_ref = await self._infra.node_cache.get(self._doc_id, node.key, fingerprint)
        if output_ref is None:
            self._from_cache[node.key] = False
            return None

        # 3. Hit — decode the typed stage output from S3 and capture it for the EngineResult.
        output = await StageOutputCodec.decode(node.key, output_ref, self._infra.object_store)
        self._from_cache[node.key] = True
        self._stage_outputs[node.key] = output
        return output

    async def cache_store(
        self, node: AbstractNode, ctx: ContextBase, output: NodeOutput, run: RunContext
    ) -> None:
        """Encode a freshly-run stage's output to S3 and record it in the node cache."""
        fingerprint = self._fingerprints[node.key]
        source_hash = self._source_hash_for(node.key, ctx, output)
        output_ref = await StageOutputCodec.encode(
            node.key, output, source_hash, fingerprint, self._infra.object_store
        )
        await self._infra.node_cache.put(self._doc_id, node.key, fingerprint, output_ref)

    async def after_node(
        self, node: AbstractNode, ctx: ContextBase, output: NodeOutput, run: RunContext
    ) -> None:
        """Capture stage outputs; persist IR after enrich and flush embed traces after embed/index."""
        if node.KIND != NodeKind.STAGE:
            return
        # 1. Capture every freshly-run stage output (cache hits are captured in cache_load).
        self._stage_outputs[node.key] = output
        # 2. After enrich, persist the IR blocks + flip to 'parsed' with the derived implicit_meta.
        if node.key == "enrich":
            await self._persist_after_enrich(output)
        # 3. After embed/index, flush the embed-chain traces onto the document lineage.
        elif node.key == "embed_index":
            await IngestPersistHelpers.flush_embed_traces(
                self._infra, self._doc_id, output.embed_result
            )

    async def on_error(self, node: AbstractNode, exc: Exception, run: RunContext) -> None:
        """Mark a failed NODE_CACHED stage's row 'failed' so the next run re-executes it."""
        if node.KIND != NodeKind.STAGE or node.key not in _NODE_CACHED_STAGES:
            return
        fingerprint = self._fingerprints.get(node.key)
        if not fingerprint:
            return
        await self._infra.node_cache.fail(self._doc_id, node.key, fingerprint)

    async def mark_failed(self, run: RunContext) -> None:
        """Flip the document to the terminal 'failed' status."""
        await IngestPersistHelpers.mark_failed(self._infra, self._doc_id)

    async def mark_done(self, run: RunContext) -> None:
        """Flip the document to the terminal 'done' status (every stage succeeded)."""
        await IngestPersistHelpers.mark_done(self._infra, self._doc_id)

    def _source_hash_for(self, key: str, ctx: ContextBase, output: NodeOutput) -> str:
        """
        Resolve the content address used as the codec's S3 key prefix for a NODE_CACHED stage.

        Args:
            key (str): The stage key (``ingest`` / ``parse`` / ``enrich``).
            ctx (ContextBase): The stage's resolved context (parse carries source_hash on its input).
            output (NodeOutput): The stage output (ingest carries source_hash; enrich on its IR).

        Returns:
            str: The content address (falls back to the run-level source hash).
        """
        if key == "ingest":
            return getattr(output, "source_hash", self._source_hash)
        if key == "parse":
            return getattr(ctx.input, "source_hash", None) or output.ir.source_hash
        if key == "enrich":
            return output.ir.source_hash
        return self._source_hash

    async def _persist_after_enrich(self, enrich_output: NodeOutput) -> None:
        """Persist IR blocks + 'parsed' from the captured ingest / parse / enrich stage outputs."""
        ingest_output = self._stage_outputs["ingest"]
        parse_output = self._stage_outputs["parse"]
        await IngestPersistHelpers.persist_after_enrich(
            infra=self._infra,
            doc_id=self._doc_id,
            source_hash=self._source_hash,
            ingest_output=ingest_output,
            parse_result=parse_output.parse_result,
            ir=enrich_output.ir,
            ingest_fp=self._fingerprints["ingest"],
            parse_fp=self._fingerprints["parse"],
            enrich_result=enrich_output.enrich_result,
            enrich_fp=self._fingerprints["enrich"],
            parse_cache_hit=self._from_cache.get("parse", False),
            enrich_cache_hit=self._from_cache.get("enrich", False),
        )


__all__ = ["WorkerEngineHooks"]
