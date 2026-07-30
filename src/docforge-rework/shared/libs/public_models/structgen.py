# ====== Code Summary ======
# The structured-generation vocabulary: the request/response artefacts of the generic ``structgen``
# capability family. A GenerationRequest is ONE structured-output LLM call fully described — the
# fields to fill (each a contract spec + its instruction), the text to extract from, and the primary
# endpoint the call targets. GeneratedValues is the call's coerced result, carried back keyed to the
# chunk (or the document) it belongs to. These are the metagen analogue of the enrich ForEach's
# FigureItem → EnrichmentEntry pair: prep emits requests, the capability chain turns each into values.

# ====== Standard Library Imports ======
from typing import Any

# ====== Third-Party Library Imports ======
from pydantic import Field

# ====== Local Project Imports ======
from .base import Artifact
from .contract import MetadataFieldSpec
from .endpoint import OpenAICompatConfig


class GenerationField(Artifact):
    """
    One field a structured-generation call must fill.

    Attributes:
        spec (MetadataFieldSpec): The contract field (its name and type drive both the output
            JSON-schema fragment and the strict coercion of the returned value).
        instruction (str): The per-field prompt handed to the model (resolved by the prep node
            from the target's prompt, or auto-derived from the field's name and type).
    """

    spec: MetadataFieldSpec = Field(
        description="The contract field to fill — its type forces the output shape and coercion."
    )
    instruction: str = Field(description="The per-field instruction handed to the model.")


class GenerationRequest(Artifact):
    """
    One structured-output LLM call, fully described — the item a metagen ForEach iterates.

    Attributes:
        request_id (str): Stable id used to match the produced values back to their source.
        chunk_id (str | None): The chunk these values belong to; ``None`` for a document-scope call.
        system_prompt (str): The generation instruction shared by the whole call.
        text (str): The text the values are extracted from (a chunk's enriched text, or the
            document view).
        fields (list[GenerationField]): The fields this single call must fill (a grouping of
            targets sharing one endpoint, or one field in per-field mode).
        endpoint (OpenAICompatConfig): The RESOLVED primary endpoint — the node default or the
            target's per-field override (a chain step may still override it downstream).
        temperature (float): Sampling temperature for the call.
        max_tokens (int): Generation cap for the call.
    """

    request_id: str = Field(
        description="Stable id matching the produced values back to their source."
    )
    chunk_id: str | None = Field(
        default=None, description="The chunk these values belong to; None for document scope."
    )
    system_prompt: str = Field(description="The generation instruction shared by the call.")
    text: str = Field(description="The text the values are extracted from.")
    fields: list[GenerationField] = Field(
        default_factory=list, description="The fields this single call must fill."
    )
    endpoint: OpenAICompatConfig = Field(
        description="The resolved primary endpoint (node default or per-field override)."
    )
    temperature: float = Field(default=0.0, description="Sampling temperature for the call.")
    max_tokens: int = Field(default=512, description="Generation cap for the call.")


class GeneratedValues(Artifact):
    """
    The coerced result of one structured-generation call — a metagen ForEach body terminal.

    Attributes:
        request_id (str): The id of the request this answers (echoed from the request).
        chunk_id (str | None): The chunk the values belong to; ``None`` for document scope.
        values (dict): Field name → coerced value; a field the model could not usably fill is
            absent (never a wrong-typed value).
    """

    request_id: str = Field(description="The id of the request this answers.")
    chunk_id: str | None = Field(
        default=None, description="The chunk the values belong to; None for document scope."
    )
    values: dict[str, Any] = Field(
        default_factory=dict, description="Field name → coerced value (unusable fields absent)."
    )


__all__ = ["GenerationField", "GenerationRequest", "GeneratedValues"]
