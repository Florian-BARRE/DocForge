# ====== Code Summary ======
# Shared result dataclasses for all provider capabilities.
# Each result type is produced by exactly one provider protocol (OCR, VLM, embed, etc.)
# and consumed by the stage engine and chain gate.
# Kept separate from interfaces.py (Protocols) to allow adapters to import results
# without pulling in Protocol dependencies.

# ====== Standard Library Imports ======
from __future__ import annotations

from typing import Any

# ====== Third-Party Library Imports ======
from pydantic import BaseModel

# ====== Internal Project Imports ======
# (none — leaf module; all other capability modules may import from here)

# ====== Local Project Imports ======
# (none)


class ConvertResult(BaseModel):
    """Output of a document conversion (office/web → PDF)."""

    pdf_bytes: bytes
    page_count: int


class OcrHint(BaseModel):
    """Context passed to an OCR provider to guide extraction."""

    language: str | None = None
    dpi: int = 300


class OcrResult(BaseModel):
    """Output of an OCR call on a single image region."""

    text: str
    confidence: float  # [0, 1] — used to decide escalation in the provider chain
    language: str | None = None

    def score(self) -> float | None:
        """ScoredResult — OCR escalation uses the provider's avg per-character confidence."""
        return self.confidence


class VlmResult(BaseModel):
    """
    Output of a VLM description call.

    The ``quality`` field encodes the in-adapter heuristic used by the chain gate:
      • ``1.0`` — structured output was requested and is present + non-empty
      • ``0.5`` — only a description was returned (no schema / partial structured output)
      • ``0.0`` — the provider raised (the chain wrapper captures this case before
        the result is constructed; ``0.0`` is reserved as a sentinel)

    See ``providers/vlm/base.py`` for the helper that computes the value.
    """

    description: str
    structured: dict[str, Any] | None = None
    quality: float = 0.5

    def score(self) -> float | None:
        """ScoredResult — heuristic quality estimate populated by the adapter."""
        return self.quality


class EmbedResult(BaseModel):
    """Output of a text embedding call (dense + optional sparse for hybrid search)."""

    vectors: list[list[float]]              # one dense vector per input text
    sparse: list[dict[int, float]] | None = None  # one BM25 sparse map per text (token_id → weight)
    model: str
    quality: float = 1.0  # embeddings are binary success/fail — gate escalation flows via attempt.error

    def score(self) -> float | None:
        """ScoredResult — embed success is binary; a successful call returns 1.0."""
        return self.quality


class RerankResult(BaseModel):
    """Output of a reranking call."""

    scores: list[float]  # relevance score per input document, same order as input


__all__ = [
    "ConvertResult",
    "EmbedResult",
    "OcrHint",
    "OcrResult",
    "RerankResult",
    "VlmResult",
]
