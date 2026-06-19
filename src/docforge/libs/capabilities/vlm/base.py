# ====== Code Summary ======
# Abstract base class for all VLM (vision-language model) providers.
# Every VLM provider takes image bytes and returns a natural-language description.

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from libs.capabilities.interfaces import VlmResult


class VlmProvider(ABC):
    """
    Abstract base class for all vision-language model (VLM) providers.

    VLM providers generate retrieval-optimised descriptions of figures
    (charts, diagrams, photos).  They support two modes:
    - Prose description (default) — optimised for semantic search.
    - Structured extraction (schema != None) — chart-to-data JSON output.

    Anti-hallucination grounding: when `grounding` is provided (OCR text
    extracted from the same image), the model is instructed to stay strictly
    within that text — no invented numbers, labels, or values.

    Class attributes:
        name (str): Provider identifier used in logs.
        version (str): Model version / identifier string.
        runs_on (str): \"local\" (self-hosted) or \"remote\" (cloud API).
        cost_per_call (float): Estimated USD cost per API call (0.0 for local).
    """

    name: str
    version: str
    runs_on: str
    cost_per_call: float

    @abstractmethod
    async def describe(
        self,
        img_bytes: bytes,
        grounding: str | None = None,
        schema: dict[str, Any] | None = None,
    ) -> VlmResult:
        """
        Generate a description (and optionally structured data) for an image.

        Args:
            img_bytes (bytes): PNG or JPEG image bytes.
            grounding (str | None): OCR text to constrain the description.
            schema (dict | None): JSON schema for structured output (chart-to-data).

        Returns:
            VlmResult: Prose description + optional structured dict.
        """
        ...
