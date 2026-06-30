# ====== Code Summary ======
# StageOutputCodec — (de)serialisation of each NODE_CACHED stage's OUTPUT model to / from S3, so a
# node-cache hit can reconstruct the typed Output without re-running the stage. It ports the legacy
# cache_codec / cache_encoder, RETARGETED to the new node-engine Output shapes:
#   - ingest: the whole IngestStageIngestOutput meta JSON (no inline PDF bytes — the parse stage's
#     fetch-pdf step re-downloads the PDF by ``pdf_key``, so the legacy pdf_bytes lazy-load is gone).
#   - parse: the IR JSON + a meta JSON carrying the ParseResult refs (markdown + figure crop keys).
#   - enrich: the enriched IR JSON + a meta JSON carrying ALL eight EnrichResult counters (the legacy
#     enrich meta only persisted four; the new EnrichResult adds the per-cache-hit counters).
# S3 keys reuse S3Helpers so cached artefacts stay byte-compatible with the content-addressed layout.

# ====== Standard Library Imports ======
import json

# ====== Third-Party Library Imports ======
from loggerplusplus import loggerplusplus

# ====== Internal Project Imports ======
from common_libs.domain.ir.models import DocumentIR
from common_libs.pipelines import NodeOutput
from common_libs.pipelines.core.ingest.stages.enrich.io import IngestStageEnrichOutput
from common_libs.pipelines.core.ingest.stages.enrich.result import EnrichResult
from common_libs.pipelines.core.ingest.stages.ingest.io import IngestStageIngestOutput
from common_libs.pipelines.core.ingest.stages.parse.io import IngestStageParseOutput
from common_libs.pipelines.core.ingest.stages.parse.result import ParseResult
from common_libs.storage.s3.helpers import S3Helpers

# The canonical content type of every meta / IR artefact uploaded by the codec.
_JSON = "application/json"


class StageOutputCodec:
    """
    Static (de)serialiser of NODE_CACHED stage outputs to / from the object store.

    ``encode`` uploads a freshly-run stage's output artefacts and returns the meta key recorded in the
    node cache; ``decode`` reconstructs the typed Output from that meta key on a cache hit. Both
    dispatch on the stage key (``ingest`` / ``parse`` / ``enrich``).
    """

    logger = loggerplusplus.bind(identifier="StageOutputCodec")

    def __new__(cls, *args: object, **kwargs: object) -> None:
        """Block instantiation — this is a static-only codec."""
        raise TypeError("StageOutputCodec is a static-only class and cannot be instantiated.")

    @classmethod
    async def encode(
        cls,
        key: str,
        output: NodeOutput,
        source_hash: str,
        fingerprint: str,
        s3: object,
    ) -> str:
        """
        Upload a stage's output artefacts to S3 and return the meta key for the node cache.

        Args:
            key (str): The NODE_CACHED stage key (``ingest`` / ``parse`` / ``enrich``).
            output (NodeOutput): The freshly-run stage output to serialise.
            source_hash (str): SHA-256 content address (the S3 key prefix).
            fingerprint (str): The stage's Merkle node fingerprint (the S3 key segment).
            s3 (object): The object store client (``upload(key, bytes, content_type)``).

        Returns:
            str: The meta artefact's S3 key, recorded as the node-cache ``output_ref``.

        Raises:
            ValueError: When the stage key has no codec (not a NODE_CACHED ingest stage).
        """
        if key == "ingest":
            return await cls._encode_ingest(output, source_hash, fingerprint, s3)
        if key == "parse":
            return await cls._encode_parse(output, source_hash, fingerprint, s3)
        if key == "enrich":
            return await cls._encode_enrich(output, source_hash, fingerprint, s3)
        raise ValueError(f"No node-cache codec for stage {key!r}.")

    @classmethod
    async def decode(cls, key: str, output_ref: str, s3: object) -> NodeOutput:
        """
        Reconstruct a stage's typed Output from its cached meta key.

        Args:
            key (str): The NODE_CACHED stage key (``ingest`` / ``parse`` / ``enrich``).
            output_ref (str): The cached meta artefact's S3 key (the node-cache ``output_ref``).
            s3 (object): The object store client (``download(key) -> bytes``).

        Returns:
            NodeOutput: The reconstructed typed stage Output.

        Raises:
            ValueError: When the stage key has no codec.
        """
        if key == "ingest":
            return await cls._decode_ingest(output_ref, s3)
        if key == "parse":
            return await cls._decode_parse(output_ref, s3)
        if key == "enrich":
            return await cls._decode_enrich(output_ref, s3)
        raise ValueError(f"No node-cache codec for stage {key!r}.")

    @classmethod
    async def _encode_ingest(
        cls, output: IngestStageIngestOutput, source_hash: str, fingerprint: str, s3: object
    ) -> str:
        """Serialise the ingest stage output as a single meta JSON (no inline PDF bytes)."""
        meta_key = S3Helpers.key_s0_meta(source_hash, fingerprint)
        payload = {
            "doc_id": output.doc_id,
            "source_hash": output.source_hash,
            "original_format": output.original_format,
            "original_key": output.original_key,
            "pdf_key": output.pdf_key,
            "converted": output.converted,
            "page_count": output.page_count,
            "needs_ocr": output.needs_ocr,
            "media_type": output.media_type,
            "implicit_meta": output.implicit_meta,
        }
        await s3.upload(meta_key, json.dumps(payload, separators=(",", ":")).encode("utf-8"), _JSON)
        return meta_key

    @classmethod
    async def _decode_ingest(cls, output_ref: str, s3: object) -> IngestStageIngestOutput:
        """Rebuild the ingest stage output from its meta JSON."""
        meta = json.loads(await s3.download(output_ref))
        return IngestStageIngestOutput(**meta)

    @classmethod
    async def _encode_parse(
        cls, output: IngestStageParseOutput, source_hash: str, fingerprint: str, s3: object
    ) -> str:
        """Serialise the parse IR JSON + a meta JSON carrying the ParseResult references."""
        ir_key = S3Helpers.key_ir(source_hash, fingerprint)
        await s3.upload(ir_key, output.ir.model_dump_json().encode("utf-8"), _JSON)
        meta_key = S3Helpers.key_s1_meta(source_hash, fingerprint)
        payload = {
            "ir_key": ir_key,
            "markdown_key": output.parse_result.markdown_key,
            "figure_crop_keys": output.parse_result.figure_crop_keys,
        }
        await s3.upload(meta_key, json.dumps(payload, separators=(",", ":")).encode("utf-8"), _JSON)
        return meta_key

    @classmethod
    async def _decode_parse(cls, output_ref: str, s3: object) -> IngestStageParseOutput:
        """Rebuild the parse stage output (IR + ParseResult) from its meta + IR JSON."""
        meta = json.loads(await s3.download(output_ref))
        ir = DocumentIR.model_validate_json(await s3.download(meta["ir_key"]))
        parse_result = ParseResult(
            ir=ir, markdown_key=meta["markdown_key"], figure_crop_keys=meta["figure_crop_keys"]
        )
        return IngestStageParseOutput(ir=ir, parse_result=parse_result)

    @classmethod
    async def _encode_enrich(
        cls, output: IngestStageEnrichOutput, source_hash: str, fingerprint: str, s3: object
    ) -> str:
        """Serialise the enriched IR JSON + a meta JSON carrying all eight EnrichResult counters."""
        ir_key = S3Helpers.key_ir_enriched(source_hash, fingerprint)
        await s3.upload(ir_key, output.ir.model_dump_json().encode("utf-8"), _JSON)
        meta_key = S3Helpers.key_s2_meta(source_hash, fingerprint)
        result = output.enrich_result
        payload = {
            "ir_enriched_key": ir_key,
            "figures_processed": result.figures_processed,
            "ocr_calls": result.ocr_calls,
            "vlm_calls": result.vlm_calls,
            "chart_extractions": result.chart_extractions,
            "ocr_cache_hits": result.ocr_cache_hits,
            "vlm_cache_hits": result.vlm_cache_hits,
            "classifier_calls": result.classifier_calls,
            "classifier_cache_hits": result.classifier_cache_hits,
        }
        await s3.upload(meta_key, json.dumps(payload, separators=(",", ":")).encode("utf-8"), _JSON)
        return meta_key

    @classmethod
    async def _decode_enrich(cls, output_ref: str, s3: object) -> IngestStageEnrichOutput:
        """Rebuild the enrich stage output (enriched IR + EnrichResult) from its meta + IR JSON."""
        meta = json.loads(await s3.download(output_ref))
        ir = DocumentIR.model_validate_json(await s3.download(meta["ir_enriched_key"]))
        result = EnrichResult(
            ir=ir,
            figures_processed=meta["figures_processed"],
            ocr_calls=meta["ocr_calls"],
            vlm_calls=meta["vlm_calls"],
            chart_extractions=meta["chart_extractions"],
            ocr_cache_hits=meta["ocr_cache_hits"],
            vlm_cache_hits=meta["vlm_cache_hits"],
            classifier_calls=meta["classifier_calls"],
            classifier_cache_hits=meta["classifier_cache_hits"],
        )
        return IngestStageEnrichOutput(ir=ir, enrich_result=result)


__all__ = ["StageOutputCodec"]
