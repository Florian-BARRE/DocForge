# ====== Code Summary ======
# Config for the OpenAI-compatible LLM node — the generic case: endpoint and model are set per
# collection with no vendor default. Only these two fields are re-declared to add their help text;
# the generation parameters come from BaseLlmChatConfig.

# ====== Third-Party Library Imports ======
from pydantic import Field

# ====== Internal Project Imports ======
from shared_libs.pipelines.nodes.openai_compat import OpenAICompatConfig

# ====== Local Project Imports ======
from ..base import BaseLlmChatConfig


class LlmOpenAICompatibleConfig(BaseLlmChatConfig, OpenAICompatConfig):
    """Configuration of a generic OpenAI-compatible endpoint (no vendor default)."""

    base_url: str = Field(
        description="Base URL of the OpenAI-compatible endpoint (per collection)."
    )
    model: str = Field(description="Model name to request.")


__all__ = ["LlmOpenAICompatibleConfig"]
