# ====== Code Summary ======
# Stateless helpers for the OpenAI-compatible VLM base adapter.
# Contains: the chart-to-data JSON schema constant, prompt builders,
# and the quality heuristic gate.  No HTTP, no logging, no state.

# ====== Standard Library Imports ======
from __future__ import annotations

from typing import Any

# ====== Third-Party Library Imports ======
# (none — pure Python, no external dependencies)

# ====== Internal Project Imports ======
# (none — leaf utility module)

# ====== Local Project Imports ======
# (none)


# Chart-to-data JSON schema — sent as response_format when the stage requests structured output.
CHART_DATA_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "description": {
            "type": "string",
            "description": "Concise description of the chart for retrieval.",
        },
        "table": {
            "type": "array",
            "items": {"type": "array", "items": {"type": "string"}},
            "description": "Row-major table of extracted data (first row = headers).",
        },
    },
    "required": ["description", "table"],
    "additionalProperties": False,
}


class OpenAICompatVlmHelpers:
    """
    Stateless helpers for the OpenAI-compatible VLM base class.

    Covers: system prompt assembly, user-turn text, and the in-adapter
    quality heuristic consumed by the VLM chain gate.
    """

    def __new__(cls, *args: object, **kwargs: object) -> None:
        """Block instantiation — this is a static-only helper class."""
        raise TypeError(
            "OpenAICompatVlmHelpers is a static-only class and cannot be instantiated."
        )

    @staticmethod
    def heuristic_quality(
        description: str,
        structured: dict[str, Any] | None,
        schema_requested: bool,
    ) -> float:
        """
        Score a VLM response in [0.0, 1.0] using only what the adapter sees.

        Args:
            description (str): The natural-language description returned.
            structured (dict | None): Parsed structured payload (None when schema not
                requested or JSON parsing failed).
            schema_requested (bool): Whether the caller asked for a structured response.

        Returns:
            float: 1.0 when structured output was requested and is non-empty;
                0.5 when only a non-empty description was returned;
                0.0 when neither slot carries usable content.
        """
        has_description = bool(description and description.strip())
        has_structured = isinstance(structured, dict) and len(structured) > 0
        if schema_requested and has_structured:
            return 1.0
        if has_description:
            return 0.5
        return 0.0

    @staticmethod
    def build_system_prompt(grounding: str | None, schema: dict | None) -> str:
        """
        Assemble the system prompt based on grounding/schema flags.

        Args:
            grounding (str | None): OCR text; when present, adds anti-hallucination block.
            schema (dict | None): JSON schema; when present, adds JSON-only instruction.

        Returns:
            str: System prompt string for the chat-completions request.
        """
        parts = [
            "You are a document intelligence assistant.  Describe images from professional "
            "documents (reports, presentations, research papers) in a way optimized for "
            "information retrieval.  Include axes, units, trends, extrema, key labels, and "
            "significant data points.  Be precise and concise."
        ]
        if grounding:
            parts.append(
                "\nIMPORTANT — Anti-hallucination constraint: the following OCR text was "
                "extracted directly from this image.  You MUST ground your description on "
                "this text.  Do NOT invent numbers, labels, names, or values that are absent "
                "from the OCR text:\n"
                f"<ocr_text>{grounding}</ocr_text>"
            )
        if schema:
            parts.append(
                "\nRespond ONLY with valid JSON matching the provided schema.  "
                "No preamble, no markdown fencing."
            )
        return "\n".join(parts)

    @staticmethod
    def build_user_text(grounding: str | None, schema: dict | None) -> str:
        """
        Build the user-turn instruction for the chat-completions request.

        Args:
            grounding (str | None): OCR text present when the stage provides grounding.
            schema (dict | None): JSON schema present for chart-to-data requests.

        Returns:
            str: User instruction string.
        """
        if schema:
            return (
                "Extract the structured data from this chart or graph.  "
                "Return a JSON object with a 'description' string and a 'table' array."
            )
        if grounding:
            return "Describe this figure for information retrieval, grounded on the OCR text."
        return "Describe this figure for information retrieval."


__all__ = ["CHART_DATA_SCHEMA", "OpenAICompatVlmHelpers"]
