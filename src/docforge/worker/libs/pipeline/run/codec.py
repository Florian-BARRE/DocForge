# ====== Code Summary ======
# StageOutputCodec — (de)serialisation of each NODE_CACHED stage's OUTPUT model to / from S3, so a
# node-cache hit can reconstruct the typed Output without re-running the stage. Retargeted to the v2
# flow stage Output shapes:
#   - ingest: the whole IngestStageOutput meta JSON (identity + PDF view + probe + implicit_meta; no
#     inline PDF bytes — the parse stage re-downloads the PDF by ``pdf_key``).
#   - parse: the IR JSON + a meta JSON carrying the markdown view key + the figure crop keys.
#   - enrich: the enriched IR JSON + a meta JSON carrying the eight EnrichStageOutput telemetry counters.
# S3 keys reuse S3Helpers so cached artefacts stay byte-compatible with the content-addressed layout.

# ====== Standard Library Imports ======
import json

# ====== Third-Party Library Imports ======
from loggerplusplus import loggerplusplus

# ====== Internal Project Imports ======
from common_libs.domain.ir.models import DocumentIR
from common_libs.pipelines.enrich import EnrichStageOutput
from common_libs.pipelines.flow import NodeOutput
from common_libs.pipelines.ingest import IngestStageOutput
from common_libs.pipelines.parse import ParseStageOutput
from common_libs.storage.s3.helpers import S3Helpers

# The canonical content type of every meta / IR artefact uploaded by the codec.
_JSON = "application/json"


class StageOutputCodec:
    """
    Static (de)serialiser of NODE_CACHED stage outputs to / from the object store.

    ``encode`` uploads a freshly-run stage's output artefacts and returns the meta key recorded in the
    node cache; ``decode`` reconstructs the typed Output from that meta key on a cache hit. Both
    dispatch on the stage id (``ingest`` / ``parse`` / ``enrich``).
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
            key (str): The NODE_CACHED stage id (``ingest`` / ``parse`` / ``enrich``).
            output (NodeOutput): The freshly-run stage output to serialise.
            source_hash (str): SHA-256 content address (the S3 key prefix).
            fingerprint (str): The stage's Merkle node fingerprint (the S3 key segment).
            s3 (object): The object store client (``upload(key, bytes, content_type)``).

        Returns:
            str: The meta artefact's S3 key, recorded as the node-cache ``output_ref``.

        Raises:
            ValueError: When the stage id has no codec (not a NODE_CACHED ingest stage).
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
            key (str): The NODE_CACHED stage id (``ingest`` / ``parse`` / ``enrich``).
            output_ref (str): The cached meta artefact's S3 key (the node-cache ``output_ref``).
            s3 (object): The object store client (``download(key) -> bytes``).

        Returns:
            NodeOutput: The reconstructed typed stage Output.

        Raises:
            ValueError: When the stage id has no codec.
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
        cls, output: IngestStageOutput, source_hash: str, fingerprint: str, s3: object
    ) -> str:
        """Serialise the ingest stage output as a single meta JSON (no inline PDF bytes)."""
        meta_key = S3Helpers.key_s0_meta(source_hash, fingerprint)
        payload = {
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
    async def _decode_ingest(cls, output_ref: str, s3: object) -> IngestStageOutput:
        """Rebuild the ingest stage output from its meta JSON."""
        meta = json.loads(await s3.download(output_ref))
        return IngestStageOutput(**meta)

    @classmethod
    async def _encode_parse(
        cls, output: ParseStageOutput, source_hash: str, fingerprint: str, s3: object
    ) -> str:
        """Serialise the parse IR JSON + a meta JSON carrying the markdown + figure crop keys."""
        ir_key = S3Helpers.key_ir(source_hash, fingerprint)
        await s3.upload(ir_key, output.ir.model_dump_json().encode("utf-8"), _JSON)
        meta_key = S3Helpers.key_s1_meta(source_hash, fingerprint)
        payload = {
            "ir_key": ir_key,
            "markdown_key": output.markdown_key,
            "figure_crop_keys": output.figure_crop_keys,
        }
        await s3.upload(meta_key, json.dumps(payload, separators=(",", ":")).encode("utf-8"), _JSON)
        return meta_key

    @classmethod
    async def _decode_parse(cls, output_ref: str, s3: object) -> ParseStageOutput:
        """Rebuild the parse stage output (IR + markdown key + crop keys) from its meta + IR JSON."""
        meta = json.loads(await s3.download(output_ref))
        ir = DocumentIR.model_validate_json(await s3.download(meta["ir_key"]))
        return ParseStageOutput(
            ir=ir, markdown_key=meta["markdown_key"], figure_crop_keys=meta["figure_crop_keys"]
        )

    @classmethod
    async def _encode_enrich(
        cls, output: EnrichStageOutput, source_hash: str, fingerprint: str, s3: object
    ) -> str:
        """Serialise the enriched IR JSON + a meta JSON carrying the eight telemetry counters."""
        ir_key = S3Helpers.key_ir_enriched(source_hash, fingerprint)
        await s3.upload(ir_key, output.ir.model_dump_json().encode("utf-8"), _JSON)
        meta_key = S3Helpers.key_s2_meta(source_hash, fingerprint)
        payload = {
            "ir_enriched_key": ir_key,
            "figures_processed": output.figures_processed,
            "classifier_calls": output.classifier_calls,
            "classifier_cache_hits": output.classifier_cache_hits,
            "ocr_calls": output.ocr_calls,
            "ocr_cache_hits": output.ocr_cache_hits,
            "vlm_calls": output.vlm_calls,
            "vlm_cache_hits": output.vlm_cache_hits,
            "chart_extractions": output.chart_extractions,
        }
        await s3.upload(meta_key, json.dumps(payload, separators=(",", ":")).encode("utf-8"), _JSON)
        return meta_key

    @classmethod
    async def _decode_enrich(cls, output_ref: str, s3: object) -> EnrichStageOutput:
        """Rebuild the enrich stage output (enriched IR + counters) from its meta + IR JSON."""
        meta = json.loads(await s3.download(output_ref))
        ir = DocumentIR.model_validate_json(await s3.download(meta["ir_enriched_key"]))
        return EnrichStageOutput(
            ir=ir,
            figures_processed=meta["figures_processed"],
            classifier_calls=meta["classifier_calls"],
            classifier_cache_hits=meta["classifier_cache_hits"],
            ocr_calls=meta["ocr_calls"],
            ocr_cache_hits=meta["ocr_cache_hits"],
            vlm_calls=meta["vlm_calls"],
            vlm_cache_hits=meta["vlm_cache_hits"],
            chart_extractions=meta["chart_extractions"],
        )


__all__ = ["StageOutputCodec"]
