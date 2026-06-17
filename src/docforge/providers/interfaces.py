# ====== Code Summary ======
# Provider Protocol interfaces: one per capability (convert, parse, ocr, vlm, embed, rerank).
# All ML bricks implement one of these Protocols — swap backend by changing the config,
# not the calling code.  The OpenAI-compatible chat-completions shape is the lingua franca
# for remote VLM/LLM providers (vLLM, Ollama, TGI, OpenAI, Mistral, OpenRouter…).

# ====== Standard Library Imports ======
from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

# ====== Third-Party Library Imports ======
from pydantic import BaseModel

# ====== Internal Project Imports ======
from ir.models import DocumentIR


# ─── Shared result types ────────────────────────────────────────────────────


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


class VlmResult(BaseModel):
    """Output of a VLM description call."""

    description: str
    # Structured output when schema was requested (e.g. chart-to-data)
    structured: dict[str, Any] | None = None


class EmbedResult(BaseModel):
    """Output of a text embedding call (dense + optional sparse for hybrid search)."""

    vectors: list[list[float]]              # one dense vector per input text
    sparse: list[dict[int, float]] | None = None  # one BM25 sparse map per text (token_id → weight)
    model: str


class RerankResult(BaseModel):
    """Output of a reranking call."""

    scores: list[float]  # relevance score per input document, same order as input


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
