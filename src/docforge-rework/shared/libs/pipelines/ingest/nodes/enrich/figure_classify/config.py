# ====== Code Summary ======
# Config of the figure_classify node: the cheap HEURISTICS (full-page crop → scanned_text, tiny
# crop → decorative) and the VLM endpoint used for everything the heuristics cannot decide. The
# classifier's kind drives the WhenEquals switch — its score can gate an escalation.

# ====== Third-Party Library Imports ======
from pydantic import Field

# ====== Internal Project Imports ======
from shared_libs.pipelines.nodes.openai_compat import OpenAICompatConfig


class FigureClassifyConfig(OpenAICompatConfig):
    """Heuristic thresholds + the classification model endpoint."""

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
    model: str = Field(description="Vision-capable model used to classify.")
    temperature: float = Field(default=0.0, ge=0.0, le=2.0, description="Sampling temperature.")
    max_tokens: int = Field(default=10, gt=0, description="Generation cap (one class word).")


__all__ = ["FigureClassifyConfig"]
