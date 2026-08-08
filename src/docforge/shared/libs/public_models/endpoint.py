# ====== Code Summary ======
# OpenAICompatConfig — the ONE declaration of what reaching an OpenAI-compatible endpoint takes
# (base_url, key, model, timeout). It is shared VOCABULARY (pure data), so it lives here with the
# rest of the artefact models: node configs mix it in (vlm, figure_classify, contextualize/llm,
# chunker/semantic, metagen) and artefacts embed it (a GenerationRequest carries its endpoint). The
# CLIENT FACTORY that turns this config into a live LangChain client stays in the pipelines layer
# (shared_libs.pipelines.nodes.openai_compat), which re-exports this class for its existing consumers.
#
# It subclasses NodeConfig, which also lives in public_models (base.py) — so this module makes NO
# upward import into the pipelines layer and public_models stays a clean bottom vocabulary layer.

# ====== Third-Party Library Imports ======
from pydantic import Field, field_validator

# ====== Internal Project Imports ======
from shared_libs.public_models.base import TimeoutRetryConfig


class OpenAICompatConfig(TimeoutRetryConfig):
    """The endpoint fields shared by every OpenAI-compatible consumer.

    The timeout/retry/preflight knobs come from ``TimeoutRetryConfig`` (``timeout_seconds`` keeps its
    30 s default here); this class only adds the endpoint identity (url, key, model).
    """

    base_url: str = Field(
        description="OpenAI-compatible endpoint (e.g. http://vllm:8000/v1 or https://api.openai.com/v1)."
    )
    api_key: str = Field(default="", description="API key for the endpoint (may be empty locally).")
    model: str = Field(description="Model name served by the endpoint.")

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
