# ====== Code Summary ======
# The config every VLM provider node shares: the SYSTEM PROMPT that drives what the description
# must be (per figure class: photo caption, scanned-text complement, diagram rewriting, chart
# reading…), generation knobs, and the chart-to-table switch (the response must then end with a
# fenced ```table``` block, parsed into rows). Children add their provider specifics (endpoint,
# api key, model).

# ====== Third-Party Library Imports ======
from pydantic import Field

# ====== Internal Project Imports ======
from shared_libs.pipelines.base import NodeConfig


class BaseVlmConfig(NodeConfig):
    """Shared VLM config — the prompt IS the behaviour."""

    system_prompt: str = Field(
        default="Describe this image precisely, for retrieval purposes.",
        description="Drives the description (per figure class: caption, diagram rewriting, …).",
    )
    max_tokens: int = Field(default=512, gt=0, description="Generation cap for the description.")
    temperature: float = Field(default=0.2, ge=0.0, le=2.0, description="Sampling temperature.")
    extract_table: bool = Field(
        default=False,
        description="Ask the model to ALSO output the underlying data as a fenced ```table``` "
        "block (chart-to-table); the block is parsed into rows and stripped from the description.",
    )


__all__ = ["BaseVlmConfig"]
