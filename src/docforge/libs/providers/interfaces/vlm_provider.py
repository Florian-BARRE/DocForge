# ====== Code Summary ======
# VlmProvider Protocol — defines the interface for vision-language model backends that
# generate text descriptions of images. Follows the OpenAI chat-completions shape so local
# (vLLM, Ollama) and remote (OpenAI, Mistral, OpenRouter) providers are interchangeable.

# ====== Standard Library Imports ======
from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

# ====== Third-Party Library Imports ======
# (none — Protocol and result types only)
# ====== Internal Project Imports ======
from libs.capabilities.results import VlmResult

# ====== Local Project Imports ======
# (none)


@runtime_checkable
class VlmProvider(Protocol):
    """
    Generates a text description of an image, optionally grounded on OCR output.

    Follows the OpenAI chat-completions shape — local (vLLM, Ollama) and remote
    (OpenAI, Mistral, OpenRouter) providers are interchangeable via base_url + model.
    """

    name: str
    version: str
    runs_on: str
    cost_per_call: float

    async def describe(
        self,
        img_bytes: bytes,
        grounding: str | None = None,
        schema: dict[str, Any] | None = None,
    ) -> VlmResult:
        """
        Describe an image, optionally constrained to a JSON schema.

        Args:
            img_bytes (bytes): PNG or JPEG image bytes.
            grounding (str | None): OCR text to ground the description (anti-hallucination).
            schema (dict | None): JSON schema for structured output (chart-to-data).

        Returns:
            VlmResult: Natural-language description (+ structured payload when schema given).
        """
        ...
