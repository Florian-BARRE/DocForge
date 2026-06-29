# ====== Code Summary ======
# Pydantic request/response models for the metagen preview sub-resource. A preview validates a
# generated field's prompt by running ONE LLM call over either an existing chunk's text (chunk_id)
# or an ad-hoc sample (sample_text) — exactly one of the two must be supplied.

# ====== Standard Library Imports ======
import uuid
from typing import Any

# ====== Third-Party Library Imports ======
from pydantic import BaseModel, Field, model_validator


class MetagenPreviewRequest(BaseModel):
    """
    Request for POST /collections/{id}/metagen/preview.

    Exactly one content source must be given: ``chunk_id`` (preview against a persisted chunk's
    text) or ``sample_text`` (preview against ad-hoc text before any ingestion).

    Attributes:
        field_name (str): The generated metadata field to preview (must have a bound metagen target).
        chunk_id (uuid.UUID | None): A persisted chunk to use as the content source.
        sample_text (str | None): Ad-hoc text to use as the content source.
    """

    field_name: str = Field(..., min_length=1, description="Generated field to preview.")
    chunk_id: uuid.UUID | None = Field(default=None, description="Persisted chunk as content source.")
    sample_text: str | None = Field(default=None, description="Ad-hoc text as content source.")

    @model_validator(mode="after")
    def _exactly_one_source(self) -> "MetagenPreviewRequest":
        """Enforce exactly one of chunk_id / sample_text (xor)."""
        # 1. Reject the ambiguous (both) and the empty (neither) cases — the caller must pick one.
        has_chunk = self.chunk_id is not None
        has_text = bool(self.sample_text and self.sample_text.strip())
        if has_chunk == has_text:
            raise ValueError("Provide exactly one of 'chunk_id' or 'sample_text'.")
        return self


class MetagenPreviewResponse(BaseModel):
    """
    Response for a metagen preview — the generated value plus diagnostics.

    Attributes:
        field_name (str): The previewed field.
        scope (str): The target's generation scope ("chunk" / "document").
        value (Any): The generated value (None when the LLM returned null or the chain degraded).
        raw (dict): The full parsed JSON object the LLM returned.
        token_estimate (int): Coarse total token estimate (input proxy + output budget).
        cost_estimate (float): Coarse USD cost estimate for this single call.
        provider (str | None): The provider that produced the value (None on a degraded chain).
        degraded (bool): True when the chain exhausted and returned an empty/best-effort result.
    """

    field_name: str
    scope: str
    value: Any = None
    raw: dict[str, Any] = Field(default_factory=dict)
    token_estimate: int = 0
    cost_estimate: float = 0.0
    provider: str | None = None
    degraded: bool = False
