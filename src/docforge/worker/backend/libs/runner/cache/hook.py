# ====== Code Summary ======
# StageCacheHook — the worker-side implementation of the engine's CacheHook seam: ALL cache I/O lives
# here, so the engine and every node stay pure. Built once per run from the normalised blob (the
# healed, post-BlobNormalizer topology), it maps each cacheable root stage id to the facts a key
# needs (family/kind/CACHE_VERSION/config subtree/Produces type/artifact type). ``before`` computes
# the Merkle key, looks the artefact up, and on a HIT loads + deserialises the stored bytes and bumps
# the row (skipping the node's run); a MISS remembers the key. ``after`` serialises a freshly-run
# node's output, content-hashes it and stores bytes + pointer. A per-stage report (hit/miss/stored)
# is accumulated for the job. The hook NEVER raises into the engine — a store hiccup degrades to a
# miss next time, never a failed run.

# ====== Standard Library Imports ======
import uuid
from dataclasses import dataclass

# ====== Third-Party Library Imports ======
from loggerplusplus import LoggerClass
from pydantic import BaseModel

# ====== Internal Project Imports ======
from shared_libs.pipelines.base import NodeInput, NodeOutput
from shared_libs.pipelines.engine import ENGINE_CACHE_EPOCH
from shared_libs.pipelines.registry import NodeRegistry
from shared_libs.services.db import Database
from shared_libs.services.db.postgresql.tables import ArtifactCache, ArtifactType

# ====== Local Project Imports ======
from .codec import ArtifactCodec
from .keys import CacheKeyBuilder

# Which cached-artefact type a cacheable family produces. A family absent here is treated as
# not-cacheable this slice even if a node in it were flagged CACHEABLE (defensive: parse-IR only).
_ARTIFACT_TYPE_BY_FAMILY = {"parser": ArtifactType.PARSE_IR}


@dataclass(slots=True)
class _CacheableStage:
    """The per-stage facts the hook needs to key, (de)serialise and attribute a cached artefact."""

    family: str
    kind: str
    cache_version: str
    config: dict
    produces: type[BaseModel]
    artifact_type: ArtifactType


class StageCacheHook(LoggerClass):
    """The worker's stage-cache seam — key, look up, serve or store, and report; all I/O here."""

    def __init__(
        self,
        blob: dict,
        collection_id: uuid.UUID,
        document_id: uuid.UUID,
        database: Database,
    ) -> None:
        """
        Args:
            blob (dict): The normalised (healed) pipeline blob — its ROOT nodes are the stages.
            collection_id (uuid.UUID): The owning collection (folded into every key — isolation).
            document_id (uuid.UUID): The document being ingested (attribution on stored rows).
            database (Database): The data-layer façade (its ``artifact_cache`` facade does the I/O).
        """
        LoggerClass.__init__(self)
        self._collection_id = collection_id
        self._document_id = document_id
        self._facade = database.artifact_cache
        self._stages = self.__index_cacheable_stages(blob)
        # node_id -> computed key, remembered on a miss so ``after`` never re-hashes the input.
        self._keys: dict[str, str] = {}
        # node_id -> "hit" | "miss" | "stored" | "store_failed" (surfaced on the job).
        self._report: dict[str, str] = {}

    @property
    def report(self) -> dict[str, str]:
        """Per-stage cache outcome (node id → hit/miss/stored) — read by the worker for the job."""
        return dict(self._report)

    @staticmethod
    def __index_cacheable_stages(blob: dict) -> dict[str, _CacheableStage]:
        """Map each root stage id that is a registered cacheable node to its keying facts."""
        stages: dict[str, _CacheableStage] = {}
        for node in blob.get("nodes", []):
            family, kind = node.get("family"), node.get("kind")
            if not family or not kind or family not in _ARTIFACT_TYPE_BY_FAMILY:
                continue
            try:
                node_class = NodeRegistry.get(family, kind)
            except KeyError:
                continue
            if not getattr(node_class, "CACHEABLE", False):
                continue
            stages[node["id"]] = _CacheableStage(
                family=family,
                kind=kind,
                cache_version=getattr(node_class, "CACHE_VERSION", "0"),
                config=dict(node.get("config") or {}),
                produces=node_class.Produces,
                artifact_type=_ARTIFACT_TYPE_BY_FAMILY[family],
            )
        return stages

    def __key(self, stage: _CacheableStage, resolved_input: BaseModel) -> str:
        """Compose this stage's Merkle key for the resolved input + the owning collection."""
        return CacheKeyBuilder.build(
            family=stage.family,
            kind=stage.kind,
            cache_version=stage.cache_version,
            config=stage.config,
            resolved_input=resolved_input,
            collection_id=self._collection_id,
        )

    async def before(self, node_id: str, resolved_input: NodeInput) -> NodeOutput | None:
        """Serve the cached artefact for a stage (a HIT), or None to run it (a MISS)."""
        stage = self._stages.get(node_id)
        if stage is None:
            return None
        try:
            key = self.__key(stage, resolved_input)
            row = await self._facade.lookup(key)
            if row is None:
                self._keys[node_id] = key
                self._report[node_id] = "miss"
                return None
            data = await self._facade.load_bytes(row.content_hash)
            output = ArtifactCodec.unpack(data, stage.produces)
            await self._facade.record_hit(key)
            self._report[node_id] = "hit"
            self.logger.info(f"Stage '{node_id}' served from cache ({stage.family}/{stage.kind})")
            return output  # type: ignore[return-value]  # unpacks into the node's NodeOutput subtype
        except Exception as exc:
            # A lookup/load hiccup must NEVER fail the run — degrade to a normal (uncached) execution.
            self.logger.warning(f"Cache lookup failed for stage '{node_id}' (running it): {exc}")
            self._report[node_id] = "miss"
            return None

    async def after(self, node_id: str, resolved_input: NodeInput, output: NodeOutput) -> None:
        """Store a freshly-run cacheable stage's output (best-effort; never raises)."""
        stage = self._stages.get(node_id)
        if stage is None:
            return
        try:
            key = self._keys.get(node_id) or self.__key(stage, resolved_input)
            data = ArtifactCodec.pack(output)
            content_hash = ArtifactCodec.sha256(data)
            row = ArtifactCache(
                cache_key=key,
                content_hash=content_hash,
                stage_key=f"{stage.family}/{stage.kind}/{stage.cache_version}",
                artifact_type=stage.artifact_type,
                engine_version=f"{stage.cache_version}.{ENGINE_CACHE_EPOCH}",
                document_id=self._document_id,
                collection_id=self._collection_id,
                size_bytes=len(data),
            )
            await self._facade.store(row, data)
            self._report[node_id] = "stored"
            self.logger.info(f"Stage '{node_id}' cached ({len(data)} bytes)")
        except Exception as exc:
            # Storing is an optimisation — a failure just means the next run recomputes. Keep the run.
            self.logger.warning(f"Cache store failed for stage '{node_id}' (kept run): {exc}")
            self._report[node_id] = "store_failed"


__all__ = ["StageCacheHook"]
