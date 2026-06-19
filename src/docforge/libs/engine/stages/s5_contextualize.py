# ====== Code Summary ======
# S5 — Contextualization stage.
# Fills embed_text on each chunk using the document title + heading breadcrumb + chunk body.
# The body is the chunk's raw_text, which S4 already assembled per chunk kind (text sections,
# figure/table with co-located caption + OCR/description/chart data) — so S5 stays uniform.

# ====== Standard Library Imports ======
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

# ====== Third-Party Library Imports ======
from loggerplusplus import LoggerClass

# ====== Internal Project Imports ======
from libs.core.ir.chunk import Chunk
from libs.core.ir.models import DocumentIR


@dataclass(slots=True)
class S5Result:
    """
    Output of the S5 contextualization stage.

    Attributes:
        chunks (list[Chunk]): Chunks with embed_text populated.
        n_contextualized (int): Number of chunks that received a non-empty embed_text.
    """

    chunks: list[Chunk]
    n_contextualized: int


class S5ContextualizeStage(LoggerClass):
    """
    S5 — Chunk contextualization with configurable header template.

    For every chunk produced by S4, builds ``embed_text`` by prepending the document
    title and the heading breadcrumb trail at the point where the chunk starts.

    Default embed_text template (when both flags are on)::

        <doc_title> > <H1> > <H2>

        <chunk_body>

    The stage carries a ``ContextualizeConfig`` so operators can toggle the title /
    breadcrumb and tune the separators per collection.  ``chunk_body`` is always the
    chunk's ``raw_text`` — S4 assembles the right body per chunk kind (text sections,
    figure/table chunks with co-located caption + OCR/description/chart data), so
    contextualization stays uniform across strategies.
    """

    def __init__(self, config: Any = None) -> None:
        """
        Initialize the contextualization stage.

        Args:
            config (ContextualizeConfig | None): Header-template controls.  When None,
                a default-constructed ``ContextualizeConfig`` is used (current behaviour).
        """
        LoggerClass.__init__(self)
        # Lazy import — pipeline_config imports this module transitively in some paths.
        from libs.engine.pipeline_config import ContextualizeConfig
        self._cfg = config if config is not None else ContextualizeConfig()

    async def run(
        self,
        chunks: list[Chunk],
        ir: DocumentIR,
    ) -> S5Result:
        """
        Annotate all chunks with embed_text derived from document context.

        Args:
            chunks (list[Chunk]): S4 output chunks (embed_text = "" on entry).
            ir (DocumentIR): The enriched DocumentIR for the same document.

        Returns:
            S5Result: Chunks with embed_text set.
        """
        self.logger.info(
            f"S5 started: doc_id={ir.doc_id} chunks={len(chunks)}"
        )

        # 1. Document title (prepended once when it is not already the breadcrumb root)
        doc_title = (ir.title or "").strip()

        n_contextualized = 0
        for chunk in chunks:
            chunk.embed_text = self._build_embed_text(chunk=chunk, doc_title=doc_title)
            if chunk.embed_text:
                n_contextualized += 1

        result = S5Result(chunks=chunks, n_contextualized=n_contextualized)
        self.logger.info(
            f"S5 done: doc_id={ir.doc_id} "
            f"contextualized={n_contextualized}/{len(chunks)}"
        )
        return result

    # ─── Internal ─────────────────────────────────────────────────────────────

    def _build_embed_text(self, chunk: Chunk, doc_title: str) -> str:
        """
        Build embed_text = [doc title] + section breadcrumb + chunk body.

        The breadcrumb comes precomputed from S4 (``chunk.prov["heading_path"]``) — the
        section title therefore appears exactly once, in the breadcrumb, and is never
        repeated in the body (S4 keeps the section title out of raw_text).  The body is the
        chunk's raw_text, already assembled by S4 for every chunk kind.

        Args:
            chunk (Chunk): Chunk whose embed_text is to be filled.
            doc_title (str): Document title from IR metadata.

        Returns:
            str: The embed_text string.
        """
        cfg = self._cfg

        # 1. Section breadcrumb (precomputed by S4) — only used when include_breadcrumb=True
        breadcrumb = ""
        if cfg.include_breadcrumb and isinstance(chunk.prov, dict):
            breadcrumb = str(chunk.prov.get("heading_path", "")).strip()

        # 2. Prepend the doc title only when enabled AND not already the breadcrumb's first segment
        prefix_parts: list[str] = []
        first_crumb = breadcrumb.split(cfg.breadcrumb_separator, 1)[0] if breadcrumb else ""
        if cfg.include_doc_title and doc_title and doc_title != first_crumb:
            prefix_parts.append(doc_title)
        if breadcrumb:
            prefix_parts.append(breadcrumb)

        # 3. Assemble — context header on one line, body separated per config
        header = cfg.breadcrumb_separator.join(prefix_parts) if prefix_parts else ""
        parts = [p for p in [header, chunk.raw_text] if p.strip()]
        return cfg.header_body_separator.join(parts)
