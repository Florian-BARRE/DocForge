# ====== Code Summary ======
# The Granite-Docling parser node — Docling's VLM pipeline. A single 258M vision-language model reads
# rendered page images and predicts DocTags, replacing the modular layout→OCR→TableFormer stack. It
# implements ONLY the two Docling-family seams: _build_converter (a DocumentConverter that swaps in
# VlmPipeline + a revision-pinned GRANITEDOCLING_TRANSFORMERS spec) and _cache_key. All parse plumbing,
# the IR mapping (same DoclingIRMapper) and scoring are inherited unchanged from BaseDoclingParserNode.

# ====== Standard Library Imports ======
import threading
from typing import Any

# ====== Internal Project Imports ======
from shared_libs.pipelines.registry import NodeRegistry

# ====== Local Project Imports ======
from ..docling_base import BaseDoclingParserNode
from .config import ParserGraniteDoclingConfig


@NodeRegistry.register("parser")
class ParserGraniteDoclingNode(BaseDoclingParserNode):
    """
    Parse a PDF with Docling's Granite VLM pipeline, mapping its DocTags output to the canonical IR.

    A GPU-recommended escalation head: functionally correct on CPU (auto device fallback) but only
    throughput-viable on the -gpu worker. Wire it as a ScoreBelow step AFTER the standard docling
    parser, never in the default CPU pipeline. Table structure is VLM-predicted OTSL (coarser than
    TableFormer). The 258M weights are fetched once at runtime into the worker HF-cache volume.
    """

    KIND = "granite_docling"
    NAME = "Granite-Docling (VLM)"
    SUMMARY = "Parse a PDF into the canonical IR with Docling's Granite VLM pipeline (DocTags)."
    HOW_IT_WORKS = (
        "Renders each PDF page to an image and runs the granite-docling-258M vision-language model "
        "(Docling's VlmPipeline) to predict DocTags, then maps the resulting DoclingDocument's "
        "blocks, tables, figures and provenance into the DocumentIR via the SAME mapper as the "
        "standard parser. GPU-recommended (minutes/page on CPU); weights fetch once, at runtime, into "
        "the worker HF-cache volume."
    )
    Config = ParserGraniteDoclingConfig
    UNIQUE_IN_GRAPH = True
    # The VLM pipeline renders pages itself and is PDF-only: with no PDF view the base degrades to an
    # empty IR (score 0), which is the correct behaviour for an escalation step.
    NATIVE_FORMATS = frozenset()

    _PIPELINE = "vlm"
    # Own converter cache + locks so the VLM and standard flavours never share a dict/lock.
    _converters: dict[tuple[Any, ...], Any] = {}
    _build_lock = threading.Lock()
    _convert_lock = threading.Lock()

    def _cache_key(self) -> tuple[Any, ...]:
        """Identify the converter by the pinned revision + the VLM generation axes."""
        config: ParserGraniteDoclingConfig = self.config
        return (config.revision, config.force_backend_text, config.max_new_tokens)

    def _build_converter(self) -> Any:
        """Build the Granite VLM DocumentConverter with a revision-pinned granite-docling spec."""
        # 1. Lazy import — the VLM pipeline pulls heavy native/model deps; load only on a real parse.
        from docling.datamodel import vlm_model_specs
        from docling.datamodel.base_models import InputFormat
        from docling.datamodel.pipeline_options import VlmPipelineOptions
        from docling.document_converter import DocumentConverter, PdfFormatOption
        from docling.pipeline.vlm_pipeline import VlmPipeline

        config: ParserGraniteDoclingConfig = self.config
        # 2. Pin the model revision + per-page token budget onto the granite transformers spec so the
        #    HF download is reproducible; device stays "auto" (invariant #7 — no device knob here).
        vlm_options = vlm_model_specs.GRANITEDOCLING_TRANSFORMERS.model_copy(
            update={"revision": config.revision, "max_new_tokens": config.max_new_tokens}
        )
        pipeline_options = VlmPipelineOptions(
            vlm_options=vlm_options, force_backend_text=config.force_backend_text
        )
        # 3. PdfFormatOption swaps the WHOLE pipeline (VlmPipeline), not just its options.
        return DocumentConverter(
            format_options={
                InputFormat.PDF: PdfFormatOption(
                    pipeline_cls=VlmPipeline, pipeline_options=pipeline_options
                )
            }
        )


__all__ = ["ParserGraniteDoclingNode"]
