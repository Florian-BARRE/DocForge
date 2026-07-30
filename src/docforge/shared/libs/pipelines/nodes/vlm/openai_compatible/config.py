# ====== Code Summary ======
# Config of the OpenAI-compatible VLM node — the shared VLM knobs (system prompt, generation,
# chart-to-table) plus the endpoint specifics. One node covers every OpenAI-compatible vision API:
# a local vLLM serving Qwen-VL, OpenAI itself, Mistral Pixtral… only the base_url/model change.

# ====== Third-Party Library Imports ======
from pydantic import Field

# ====== Internal Project Imports ======
from shared_libs.pipelines.nodes.openai_compat import OpenAICompatConfig

# ====== Local Project Imports ======
from ..base import BaseVlmConfig


class VlmOpenAICompatibleConfig(BaseVlmConfig, OpenAICompatConfig):
    """OpenAI-compatible vision endpoint + model (endpoint fields inherited)."""

    model: str = Field(description="Vision-capable model name (e.g. Qwen/Qwen2.5-VL-7B-Instruct).")
    timeout_seconds: float = Field(default=60.0, gt=0, description="Per-request timeout (s).")


__all__ = ["VlmOpenAICompatibleConfig"]
