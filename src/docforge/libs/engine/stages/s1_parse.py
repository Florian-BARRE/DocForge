# ====== Code Summary ======
# S1 — Parse stage: Docling-or-chain → DocumentIR + figure crops → SeaweedFS.
# S1 operates on the PDF produced by S0 and never touches the original file again.
# The parser is delivered as a Chain[ParserProvider, DocumentIR] so the stage can
# escalate to a fallback parser (MinerU/Marker — Phase B) when the first provider's
# quality_score falls below the configured gate.
#
# Design note — no s1_helpers.py split attempted for _render_and_upload /
# _render_figure_crops_sync / _upload_markdown: all three carry self.logger calls
# (debug/info/warning) that are instance-bound and cannot be cleanly moved to a
# static helper without either losing log context or introducing artificial coupling.
# Pure IR transformations (chain-trace stamping, figure crop key patching) live in
# s1_helpers.py (S1Helpers) and are called from here.

# ====== Standard Library Imports ======
from __future__ import annotations

import asyncio
import hashlib
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from libs.data.storage.s3.client import S3Client

# ====== Third-Party Library Imports ======
from loggerplusplus import LoggerClass

from libs.capabilities.chain import Chain

# ====== Internal Project Imports ======
from libs.core.ir.models import DocumentIR
from libs.core.ir.serializer import MarkdownSerializer
from libs.data.storage.s3.helpers import S3Helpers

# ====== Local Project Imports ======
from .s0_ingest import S0Result
from .s1_helpers import S1Helpers


@dataclass(slots=True)
class S1Result:
    """
    Output artefacts produced by the S1 parsing stage.

    Attributes:
        ir (DocumentIR): The canonical IR, with the parse ChainTrace appended.
        markdown_key (str): Object-store key for the faithful markdown view.
        figure_crop_keys (dict[str, str]): block_id → object-store key for each figure crop.
    """

    ir: DocumentIR
    markdown_key: str
    figure_crop_keys: dict[str, str]


class S1ParseStage(LoggerClass):
    """
    S1 — Parsing and rasterization stage backed by a parser chain.

    Responsibilities:
      1. Invoke the parser chain; the first provider whose IR passes the gate wins.
      2. Persist the full attempt log on ``DocumentIR.chain_traces`` for lineage.
      3. Render each FIGURE bbox and upload the crop to SeaweedFS.
      4. Serialise the IR to markdown and upload it to SeaweedFS.

    What S1 does NOT do:
      - No OCR, no VLM, no classification (S2 territory).
      - No chunking, no embedding (S4–S6).
      - No Postgres writes (handled by the engine).

    Helper split rationale:
      Pure IR transformations (chain-trace stamping, figure crop key patching) are
      delegated to ``S1Helpers`` in ``s1_helpers.py``.  The remaining private methods
      (_render_and_upload, _render_figure_crops_sync, _upload_markdown) are kept here
      because they carry ``self.logger`` calls at debug/info/warning level; extracting
      them to a static class would either lose log context or require logger injection
      as a parameter, adding coupling for no structural gain.
    """

    _RENDER_DPI_ZOOM: float = 2.0

    def __init__(self, parse_chain: Chain[Any, Any], s3: S3Client) -> None:
        """
        Initialise S1 with its dependencies.

        Args:
            parse_chain (Chain[ParserProvider, DocumentIR]): Ordered parser chain.
            s3 (S3Client): SeaweedFS client for blob uploads.
        """
        LoggerClass.__init__(self)
        self._parse_chain = parse_chain
        self._s3 = s3
        self._md_serializer = MarkdownSerializer()

    @property
    def parse_chain(self) -> Chain[Any, Any]:
        """Expose the chain so the engine can fingerprint its signature."""
        return self._parse_chain

    async def run(self, s0: S0Result, fingerprint: str | None = None) -> S1Result:
        """
        Execute the S1 parse stage.

        Args:
            s0 (S0Result): Output from the S0 ingestion stage (PDF bytes must be set).
            fingerprint (str | None): P2 stage fingerprint used for the markdown S3 key.

        Returns:
            S1Result: The parsed IR (with chain trace), markdown key, and crop keys.

        Raises:
            RuntimeError: When every parser in the chain escalates or raises — the
                pipeline cannot proceed without an IR.
        """
        self.logger.info(
            f"S1 started: doc_id={s0.doc_id} pages={s0.page_count}"
        )

        # 1. Run the parser chain.  Each provider produces a full DocumentIR; the chain
        # stops at the first one whose quality_score passes the gate.
        outcome = await self._parse_chain.call(
            lambda p: p.parse(
                pdf_bytes=s0.pdf_bytes,
                doc_id=s0.doc_id,
                source_hash=s0.source_hash,
            )
        )
        if outcome.result is None:
            raise RuntimeError(
                f"S1 parse chain exhausted for doc_id={s0.doc_id} — "
                f"{len(outcome.attempts)} provider(s) attempted, none produced an IR. "
                f"See chain attempt logs above."
            )

        ir: DocumentIR = outcome.result

        # 2. Stamp the parse trace on the IR so every downstream consumer sees the lineage.
        ir = S1Helpers.stamp_parse_trace(ir, outcome)

        # 3. Render and upload figure crops (page screenshots are generated on the fly).
        figure_crop_keys = await self._render_and_upload(s0, ir)

        # 4. Patch figure blocks with their crop_key.
        ir = S1Helpers.patch_figure_crop_keys(ir, figure_crop_keys)

        # 5. Serialise IR → markdown → upload.
        markdown_key = await self._upload_markdown(s0, ir, fingerprint=fingerprint)

        result = S1Result(
            ir=ir,
            markdown_key=markdown_key,
            figure_crop_keys=figure_crop_keys,
        )

        self.logger.info(
            f"S1 done: doc_id={s0.doc_id} "
            f"blocks={len(ir.blocks)} figures={len(figure_crop_keys)} "
            f"final_parser={outcome.final_provider} attempts={len(outcome.attempts)}"
        )
        return result

    # ─── Private helpers ───────────────────────────────────────────────────────

    async def _render_and_upload(
        self, s0: S0Result, ir: DocumentIR
    ) -> dict[str, str]:
        """
        Crop all figure bboxes from the PDF and upload them to SeaweedFS.

        Crops are stored under a **content-addressed** key
        (``figures/by-hash/<sha256[:2]>/<sha256>.png``) so a logo or page header
        repeating across every slide of a deck only uploads — and only ever
        stores — a single PNG.  Multiple block IDs map to the same crop_key
        when their pixel bytes are bit-identical, which also gives the S2
        provider-call cache 100% hit-rate on those repeated figures.

        Returns:
            dict[str, str]: block_id → object-store key for each figure crop.
                Multiple block_ids can share the same key after dedup.
        """
        loop = asyncio.get_event_loop()
        figure_crops = await loop.run_in_executor(
            None,
            self._render_figure_crops_sync,
            s0.pdf_bytes,
            ir,
        )

        # Dedup: collapse identical (key → bytes) pairs so a 27-slide deck with
        # the same header logo issues exactly ONE PutObject, not 27.
        unique_uploads: dict[str, bytes] = {}
        for _, key, data in figure_crops:
            unique_uploads.setdefault(key, data)

        await asyncio.gather(*[
            self._s3.upload(key=key, data=data, content_type="image/png")
            for key, data in unique_uploads.items()
        ])

        if (savings := len(figure_crops) - len(unique_uploads)) > 0:
            self.logger.info(
                f"S1: figure crop dedup saved {savings} S3 uploads "
                f"({len(figure_crops)} blocks → {len(unique_uploads)} unique blobs)"
            )

        return {block_id: key for block_id, key, _ in figure_crops}

    def _render_figure_crops_sync(
        self,
        pdf_bytes: bytes,
        ir: DocumentIR,
    ) -> list[tuple[str, str, bytes]]:
        """Synchronous figure crop rendering via PyMuPDF (runs in thread pool).

        Each crop's S3 key is derived from ``sha256(crop_bytes)`` so two blocks
        whose pixel content is identical receive the same key and the upload
        step deduplicates them.
        """
        import fitz  # PyMuPDF

        figure_crops: list[tuple[str, str, bytes]] = []
        matrix = fitz.Matrix(self._RENDER_DPI_ZOOM, self._RENDER_DPI_ZOOM)

        with fitz.open(stream=pdf_bytes, filetype="pdf") as doc:
            for block in ir.figure_blocks:
                page_num = block.prov.page
                if page_num >= doc.page_count:
                    continue

                page = doc[page_num]
                page_w = page.rect.width
                page_h = page.rect.height

                x0, y0, x1, y1 = block.prov.bbox
                rx0, rx1 = sorted((x0 * page_w, x1 * page_w))
                ry0, ry1 = sorted((y0 * page_h, y1 * page_h))
                rect = fitz.Rect(rx0, ry0, rx1, ry1) & page.rect

                if rect.is_empty or rect.width < 2 or rect.height < 2:
                    self.logger.debug(f"S1: skipping degenerate figure crop for {block.id}")
                    continue

                try:
                    pix = page.get_pixmap(matrix=matrix, clip=rect, alpha=False)
                    crop_bytes = pix.tobytes("png")
                except Exception as exc:
                    self.logger.warning(f"S1: figure crop failed for {block.id}: {exc}")
                    continue

                # Content-addressed: identical pixel bytes → same S3 key.
                crop_hash = hashlib.sha256(crop_bytes).hexdigest()
                key = S3Helpers.key_figure_crop_by_hash(crop_hash)
                figure_crops.append((block.id, key, crop_bytes))

        return figure_crops

    async def _upload_markdown(
        self, s0: S0Result, ir: DocumentIR, fingerprint: str | None = None
    ) -> str:
        """Serialise the IR to faithful markdown and upload to SeaweedFS."""
        markdown_text = self._md_serializer.serialize(ir)
        serialize_fp = fingerprint or "s1_no_fingerprint"
        key = S3Helpers.key_markdown(s0.source_hash, serialize_fp)
        await self._s3.upload(
            key=key,
            data=markdown_text.encode("utf-8"),
            content_type="text/markdown; charset=utf-8",
        )
        self.logger.debug(f"Uploaded markdown → {key}")
        return key
