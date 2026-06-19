# ====== Code Summary ======
# Provider Protocol interfaces: one per capability (convert, parse, ocr, vlm, embed, rerank).
# All ML bricks implement one of these Protocols — swap backend by changing the config,
# not the calling code.  The OpenAI-compatible chat-completions shape is the lingua franca
# for remote VLM/LLM providers (vLLM, Ollama, TGI, OpenAI, Mistral, OpenRouter…).
#
# Result dataclasses live in results.py; re-exported here for backward compatibility
# so all callers that import from libs.capabilities.interfaces continue to work unchanged.

# ====== Standard Library Imports ======
from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

# ====== Third-Party Library Imports ======
# (none — Protocol and result types only need stdlib + local imports)
# ====== Internal Project Imports ======
from libs.core.ir.models import DocumentIR

# ====== Local Project Imports ======
from .results import (
    ConvertResult,
    EmbedResult,
    OcrHint,
    OcrResult,
    RerankResult,
    VlmResult,
)

# Re-export result types so existing callers (from libs.capabilities.interfaces import X)
# continue to work without modification.
__all__ = [
    "ConvertResult",
    "ConverterProvider",
    "EmbedProvider",
    "EmbedResult",
    "OcrHint",
    "OcrProvider",
    "OcrResult",
    "ParserProvider",
    "RerankProvider",
    "RerankResult",
    "VlmProvider",
    "VlmResult",
]


# ─── Provider Protocols ─────────────────────────────────────────────────────


@runtime_checkable
class ConverterProvider(Protocol):
    """Converts office/web documents to PDF (e.g. Gotenberg → LibreOffice + Chromium)."""

    name: str
    version: str

    async def convert(self, data: bytes, filename: str) -> ConvertResult:
        """
        Convert document bytes to PDF.

        Args:
            data (bytes): Raw source file bytes.
            filename (str): Original filename (extension used to pick conversion path).

        Returns:
            ConvertResult: PDF bytes and page count.
        """
        ...


@runtime_checkable
class ParserProvider(Protocol):
    """
    Parses a PDF (or natively-supported format) into a DocumentIR.

    Implementations: DoclingBackend, MinerUBackend, MarkerBackend.
    Each adapter translates backend-specific output → the canonical DocumentIR schema.
    """

    name: str
    version: str
    runs_on: str  # "cpu" | "gpu" | "remote"

    async def parse(
        self,
        pdf_bytes: bytes,
        doc_id: str,
        source_hash: str,
    ) -> DocumentIR:
        """
        Parse PDF bytes into a DocumentIR.

        Args:
            pdf_bytes (bytes): PDF content to parse.
            doc_id (str): Document UUID (written into the IR).
            source_hash (str): SHA-256 of the original file (written into the IR).

        Returns:
            DocumentIR: Fully populated intermediate representation.
        """
        ...


@runtime_checkable
class OcrProvider(Protocol):
    """Extracts text from an image region (page scan, figure, etc.)."""

    name: str
    version: str
    runs_on: str       # "cpu" | "gpu" | "remote"
    cost_per_page: float  # 0.0 for local providers

    async def extract(self, img_bytes: bytes, hint: OcrHint) -> OcrResult:
        """
        Run OCR on a single image.

        Args:
            img_bytes (bytes): PNG or JPEG image bytes.
            hint (OcrHint): Optional language / DPI context.

        Returns:
            OcrResult: Extracted text with confidence score.
        """
        ...


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


@runtime_checkable
class EmbedProvider(Protocol):
    """Produces dense (and optionally sparse) embedding vectors for text chunks."""

    name: str
    version: str
    runs_on: str
    dimension: int

    async def embed(self, texts: list[str]) -> EmbedResult:
        """
        Embed a batch of texts.

        Args:
            texts (list[str]): Input strings to embed.

        Returns:
            EmbedResult: One vector per input text.
        """
        ...


@runtime_checkable
class RerankProvider(Protocol):
    """Scores a list of candidate passages against a query for post-retrieval reranking."""

    name: str
    version: str
    runs_on: str

    async def rerank(self, query: str, docs: list[str]) -> RerankResult:
        """
        Rerank candidate passages for relevance to the query.

        Args:
            query (str): The retrieval query.
            docs (list[str]): Candidate passage texts.

        Returns:
            RerankResult: Relevance score per candidate, same order as input.
        """
        ...
