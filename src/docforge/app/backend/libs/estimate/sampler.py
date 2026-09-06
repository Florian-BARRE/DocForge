# ====== Code Summary ======
# DocumentSampler — turns a collection's document rows into the aggregated SampleStats the pure
# estimator consumes. It uses only what is cheaply on the row (page_count when ingest already set it,
# else file size) — no S3 read, no parse — so the preview stays cheap. Text-native formats derive
# their tokens straight from byte size; binary formats derive pages from byte size when no exact
# count exists yet (the uploaded-but-not-ingested case). It records how many pages were EXACT so the
# service can surface the sampling accuracy.

# ====== Standard Library Imports ======
import math
from collections.abc import Sequence

# ====== Third-Party Library Imports ======
from loggerplusplus import loggerplusplus

# ====== Internal Project Imports ======
from shared_libs.pipelines.ingest.estimate import EstimateAssumptions, SampleStats
from shared_libs.services.db.postgresql.tables import Document

# Formats whose byte size is (roughly) their text size — tokens come straight from bytes, no pages.
_TEXT_NATIVE_FORMATS = frozenset({"md", "markdown", "html", "htm", "txt", "text", "csv", "json"})


class DocumentSampler:
    """Static helper: aggregate document rows into SampleStats for the estimator."""

    logger = loggerplusplus.bind(identifier="DocumentSampler")

    def __new__(cls, *args: object, **kwargs: object) -> None:
        raise TypeError("DocumentSampler is a static-only class and cannot be instantiated.")

    @classmethod
    def aggregate(
        cls,
        documents: Sequence[Document],
        assumptions: EstimateAssumptions,
        document_count: int | None = None,
    ) -> SampleStats:
        """
        Aggregate document rows into SampleStats (pages + estimated text tokens).

        Args:
            documents (Sequence[Document]): The measured document rows.
            assumptions (EstimateAssumptions): Sampling assumptions (bytes/token, bytes/page, …).
            document_count (int | None): Total docs the estimate covers; defaults to the number
                sampled (equal ⇒ no scaling).

        Returns:
            SampleStats: The aggregated, estimator-ready statistics.
        """
        # 1. Fold each row into running totals, tracking exact-page provenance for the caveat.
        total_pages = 0.0
        total_text_tokens = 0.0
        pages_from_probe = 0
        for document in documents:
            pages, tokens, exact = cls.__measure(document, assumptions)
            total_pages += pages
            total_text_tokens += tokens
            pages_from_probe += 1 if exact else 0

        # 2. Shape the aggregate; the covered count defaults to the sample size (no scaling).
        sampled = len(documents)
        return SampleStats(
            document_count=document_count if document_count is not None else sampled,
            sampled_documents=sampled,
            total_pages=total_pages,
            total_text_tokens=total_text_tokens,
            pages_from_probe=pages_from_probe,
        )

    @classmethod
    def __measure(cls, document: Document, a: EstimateAssumptions) -> tuple[float, float, bool]:
        """
        Estimate one document's (pages, text tokens, exact_page_count) from its cheap row facts.

        Returns:
            tuple[float, float, bool]: pages, estimated text tokens, and whether the page count
                was EXACT (already set by ingest) rather than size-derived.
        """
        fmt = (document.format or "").lower().lstrip(".")

        # 1. Text-native formats: bytes ≈ characters, so tokens come straight from size; pages are
        #    a derived view (tokens / tokens_per_page), never an exact count.
        if fmt in _TEXT_NATIVE_FORMATS:
            tokens = document.file_size / a.bytes_per_token
            return tokens / a.tokens_per_page, tokens, False

        # 2. Binary formats with an EXACT page count (ingest already ran pdf_probe): trust it.
        if document.page_count:
            pages = float(document.page_count)
            return pages, pages * a.tokens_per_page, True

        # 3. Binary, not-yet-ingested: derive pages from byte size (the roughest path). Round a
        #    partial trailing page UP and floor a non-empty document to at least one page — a real
        #    document is never zero or a fractional page, so a tiny file must still carry a page of
        #    cost instead of rounding down to ~0 (which under-counts the estimate).
        if document.file_size <= 0:
            return 0.0, 0.0, False
        pages = float(max(1, math.ceil(document.file_size / a.bytes_per_page)))
        return pages, pages * a.tokens_per_page, False


__all__ = ["DocumentSampler"]
