# ====== Code Summary ======
# OpenAICompatConfig — the ONE declaration of what reaching an OpenAI-compatible endpoint takes
# (base_url, key, model, timeout). Every consumer's Config inherits it (vlm, figure_classify,
# contextualize/llm, chunker/semantic, metagen) instead of re-declaring the same four fields —
# the fields, their descriptions and their defaults can never drift apart again.

# ====== Third-Party Library Imports ======
from pydantic import Field, field_validator

# ====== Internal Project Imports ======
from shared_libs.pipelines.base import NodeConfig


class OpenAICompatConfig(NodeConfig):
    """The endpoint fields shared by every OpenAI-compatible consumer."""

    base_url: str = Field(
        description="OpenAI-compatible endpoint (e.g. http://vllm:8000/v1 or https://api.openai.com/v1)."
    )
    api_key: str = Field(default="", description="API key for the endpoint (may be empty locally).")
    model: str = Field(description="Model name served by the endpoint.")
    timeout_seconds: float = Field(default=30.0, gt=0, description="Per-request timeout (s).")

    @field_validator("base_url", "api_key", "model", mode="before")
    @classmethod
    def _strip_whitespace(cls, value: object) -> object:
        """
        Strip surrounding whitespace from endpoint credentials.

        A key pasted with a trailing newline becomes an ILLEGAL HTTP header value and
        surfaces as an opaque "Connection error" — caught in the first real e2e run.
        Keys, URLs and model names never legitimately carry surrounding whitespace.
        """
        return value.strip() if isinstance(value, str) else value


__all__ = ["OpenAICompatConfig"]
