# ====== Code Summary ======
# CacheDispatch — the per-stage node-cache artefact codec for the dynamic engine, keyed by stage
# KEY. It reuses the EXISTING CacheIOHelpers / CacheEncoder / S3Helpers so cached artefacts are
# byte-identical to (and reusable across) the legacy s012_runner path. Only the three NODE_CACHED
# ingest stages have a codec (ingest->S0, parse->S1+IR, enrich->S2+enriched IR); any other KEY is a
# no-op (load = miss, store = nothing), so a future node-cached stage without a codec simply re-runs.

# ====== Standard Library Imports ======
from __future__ import annotations

from typing import TYPE_CHECKING

# ====== Internal Project Imports ======
from common_libs.storage.s3.client import S3Client
from common_libs.storage.s3.helpers import S3Helpers

# ====== Local Project Imports ======
from ..orchestrator.cache_io import CacheIOHelpers

if TYPE_CHECKING:
    from common_libs.pipeline.stages.context import PipelineContext


class CacheDispatch:
    """
    Static per-stage node-cache codec for the dynamic engine (delegates to CacheIOHelpers).

    ``load`` reconstructs a cached stage's outputs onto the context; ``store`` uploads a freshly-run
    stage's artefacts to S3 and returns the meta key to record in the node cache. Both dispatch on
    the stage KEY; an unrecognised KEY is a no-op so unsupported NODE_CACHED stages re-run safely.
    """

    def __new__(cls, *args: object, **kwargs: object) -> None:  # type: ignore[misc]
        """Block instantiation — this is a static-only dispatcher."""
        raise TypeError("CacheDispatch is a static-only class and cannot be instantiated.")

    @staticmethod
    async def load(key: str, s3: S3Client, output_ref: str, ctx: "PipelineContext") -> bool:
        """
        Restore a cached stage's outputs from S3 onto the context.

        Args:
            key (str): The stage KEY (``ingest`` / ``parse`` / ``enrich``).
            s3 (S3Client): Object store client.
            output_ref (str): The cached artefact's S3 meta key (from the node cache).
            ctx (PipelineContext): The mutable run accumulator to populate.

        Returns:
            bool: True when the KEY has a codec and the outputs were restored; False otherwise.
        """
        if key == "ingest":
            s0 = await CacheIOHelpers.restore_s0(s3, output_ref)
            ctx.s0_result = s0
            ctx.source_hash = s0.source_hash
            return True
        if key == "parse":
            s1, ir = await CacheIOHelpers.restore_s1(s3, output_ref)
            ctx.s1_result = s1
            ctx.ir = ir
            return True
        if key == "enrich":
            s2, ir = await CacheIOHelpers.restore_s2(s3, output_ref)
            ctx.s2_result = s2
            ctx.ir = ir
            return True
        return False

    @staticmethod
    async def store(key: str, s3: S3Client, ctx: "PipelineContext", fingerprint: str) -> str | None:
        """
        Upload a freshly-run stage's artefacts to S3 and return its node-cache meta key.

        Args:
            key (str): The stage KEY (``ingest`` / ``parse`` / ``enrich``).
            s3 (S3Client): Object store client.
            ctx (PipelineContext): The mutable run accumulator (carries the stage results + IR).
            fingerprint (str): The stage's Merkle node fingerprint (part of the S3 key).

        Returns:
            str | None: The meta key to record in the node cache, or None for an uncodec'd KEY.
        """
        source_hash = ctx.source_hash or ""
        if key == "ingest":
            meta_key = S3Helpers.key_s0_meta(source_hash, fingerprint)
            await s3.upload(meta_key, CacheIOHelpers.encode_s0_meta(ctx.s0_result), "application/json")
            return meta_key
        if key == "parse":
            ir_key = S3Helpers.key_ir(source_hash, fingerprint)
            await s3.upload(ir_key, ctx.ir.model_dump_json().encode("utf-8"), "application/json")
            meta_key = S3Helpers.key_s1_meta(source_hash, fingerprint)
            await s3.upload(meta_key, CacheIOHelpers.encode_s1_meta(ctx.s1_result, ir_key), "application/json")
            return meta_key
        if key == "enrich":
            ir_key = S3Helpers.key_ir_enriched(source_hash, fingerprint)
            await s3.upload(ir_key, ctx.ir.model_dump_json().encode("utf-8"), "application/json")
            meta_key = S3Helpers.key_s2_meta(source_hash, fingerprint)
            await s3.upload(meta_key, CacheIOHelpers.encode_s2_meta(ctx.s2_result, ir_key), "application/json")
            return meta_key
        return None


__all__ = ["CacheDispatch"]
