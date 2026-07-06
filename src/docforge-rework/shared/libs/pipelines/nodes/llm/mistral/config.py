# ====== Code Summary ======
# Config for the Mistral LLM node — same chat-completions shape as the base, but with the vendor
# URL as default, a closed set of models (enum), and Mistral's 0–1 temperature range.

# ====== Standard Library Imports ======
from enum import StrEnum

# ====== Third-Party Library Imports ======
from pydantic import Field

# ====== Local Project Imports ======
from ..base import BaseLlmChatConfig


class MistralModel(StrEnum):
    """
    Selectable Mistral chat models.

    Attributes:
        SMALL: Fast, low-cost model.
        MEDIUM: Balanced model.
        LARGE: Most capable model.
    """

    SMALL = "mistral-small-latest"
    MEDIUM = "mistral-medium-latest"
    LARGE = "mistral-large-latest"


class LlmMistralConfig(BaseLlmChatConfig):
    """Configuration of the Mistral chat endpoint (vendor default URL, model choice, 0–1 temp)."""

    base_url: str = Field(default="https://api.mistral.ai/v1", description="Mistral API base URL.")
    model: MistralModel = Field(default=MistralModel.SMALL, description="Mistral model to use.")
    temperature: float = Field(default=0.0, ge=0.0, le=1.0, description="Sampling temperature (0–1).")


__all__ = ["MistralModel", "LlmMistralConfig"]
