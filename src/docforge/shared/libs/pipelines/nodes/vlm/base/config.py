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
    max_retries: int = Field(
        default=1,
        ge=0,
        description="Retries on a TRANSIENT provider error (timeout/connection/429/5xx) before "
        "giving up and letting the graph escalate. VLM calls are PAID — kept sober (1): one retry "
        "recovers a transient blip without storming. 0 disables retry.",
    )
    retry_backoff_seconds: float = Field(
        default=1.0,
        gt=0,
        description="Base delay for the exponential backoff between retries (delay = base * attempt).",
    )


__all__ = ["BaseVlmConfig"]
