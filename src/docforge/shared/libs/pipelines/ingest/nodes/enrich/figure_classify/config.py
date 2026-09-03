# ====== Code Summary ======
# Config of the figure_classify node: the cheap HEURISTICS (full-page crop → scanned_text, tiny
# crop → decorative) and the backend used for everything the heuristics cannot decide — either a
# hosted VLM (default) or a fully-local heuristic classifier (RapidOCR text density + geometry). The
# classifier's kind drives the WhenEquals switch; its score can gate an escalation. This config also
# carries ``figure_enrich_mode``, the enrich-stage topology selector the assembler reads (see below).

# ====== Standard Library Imports ======
from typing import Literal

# ====== Third-Party Library Imports ======
from pydantic import Field, field_validator

# ====== Internal Project Imports ======
from shared_libs.pipelines.nodes.openai_compat import OpenAICompatConfig


class FigureClassifyConfig(OpenAICompatConfig):
    """Heuristic thresholds + the classification backend (hosted VLM or fully-local)."""

    # The per-figure enrich topology selector. It is NOT consumed by the classify node at run time —
    # it is read by the enrich assembler to pick the ForEach body: ``classified`` keeps the
    # classify → per-class switch, ``uniform`` drops the classifier entirely and applies ONE
    # treatment (see ``uniform_treatment``) to every figure. It is surfaced HERE so the enrich stage's
    # schema-driven config form exposes the mode (the enrich stage config IS this node's config); in
    # ``uniform`` no classify node exists, so the mode round-trips from the graph topology, not from
    # this field. ``ocr_only`` is the pre-0.12 name of ``uniform`` and is still accepted on input.
    figure_enrich_mode: Literal["classified", "uniform"] = Field(
        default="classified",
        description="Enrich topology: 'classified' routes each figure by class; 'uniform' drops the "
        "classifier and applies one treatment to every figure.",
    )
    # In ``uniform`` mode, WHICH single treatment every figure runs: ``ocr`` reads the text with a
    # (local-first) OCR chain; ``vlm`` describes the image with a vision model (a configurable prompt
    # — e.g. "describe this image"). Ignored in ``classified`` mode. Like figure_enrich_mode it is an
    # assembler knob surfaced on this config, not consumed by the classify node itself.
    uniform_treatment: Literal["ocr", "vlm"] = Field(
        default="ocr",
        description="Uniform-mode treatment for every figure: 'ocr' reads text; 'vlm' describes the "
        "image with a vision model (configurable prompt).",
    )

    @field_validator("figure_enrich_mode", mode="before")
    @classmethod
    def _accept_legacy_ocr_only(cls, value: object) -> object:
        """Map the pre-0.12 ``ocr_only`` topology name onto its generalised successor ``uniform``."""
        return "uniform" if value == "ocr_only" else value

    classify_backend: Literal["vlm", "local"] = Field(
        default="vlm",
        description="Backend for figures the heuristics cannot decide: 'vlm' asks the hosted vision "
        "model; 'local' classifies fully locally (RapidOCR text density + geometry, no endpoint).",
    )
    use_heuristics: bool = Field(
        default=True,
        description="Decide the obvious cases without spending a model call.",
    )
    full_page_ratio: float = Field(
        default=0.85,
        ge=0.0,
        le=1.0,
        description="Page coverage above which the figure is a full-page scan (scanned_text).",
    )
    min_side_px: int = Field(
        default=48,
        ge=1,
        description="Crops with a side smaller than this are decorative (logos, rules, bullets).",
    )
    # base_url / model are required by OpenAICompatConfig for the VLM backend, but the LOCAL backend
    # needs no endpoint — relax them to optional defaults so a fully-local classify builds with no
    # placeholder. An empty endpoint on the VLM backend is still surfaced at edit time (a placeholder
    # notice) and fails at preflight, so relaxing the schema does not weaken the VLM contract.
    base_url: str = Field(
        default="",
        description="Vision endpoint (VLM backend only; leave empty for the local backend).",
    )
    model: str = Field(
        default="",
        description="Vision model name (VLM backend only; leave empty for the local backend).",
    )
    temperature: float = Field(default=0.0, ge=0.0, le=2.0, description="Sampling temperature.")
    max_tokens: int = Field(default=10, gt=0, description="Generation cap (one class word).")


__all__ = ["FigureClassifyConfig"]
