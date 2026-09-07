# ====== Code Summary ======
# TesseractEngine — the thin, process-shared runner for local Tesseract OCR. Unlike RapidOcrEngine it
# has NO persistent model to load: pytesseract shells out to the installed ``tesseract`` binary on
# every call, so there is nothing to build once. It keeps the same shape as the other local engine
# though — lazy native import (so the OCR family imports fine without pytesseract installed), the
# CPU-bound reading pushed OFF the event loop, and a fold that is robust to an empty result. It
# returns the RAW word-level data so the caller derives text + confidence, and does zero DB/S3 I/O.

# ====== Standard Library Imports ======
import asyncio
import io
from typing import Any

# ====== Third-Party Library Imports ======
from loggerplusplus import loggerplusplus


class TesseractEngine:
    """Static access to local Tesseract OCR (lazy native import, off-loop reads, empty-safe fold)."""

    logger = loggerplusplus.bind(identifier="TesseractEngine")

    def __new__(cls, *args: object, **kwargs: object) -> None:
        raise TypeError("TesseractEngine is a static-only class and cannot be instantiated.")

    @classmethod
    def __run_sync(cls, image: bytes, lang: str, psm: int) -> dict[str, Any]:
        """Synchronous OCR (runs in a worker thread) → Tesseract's word-level data dict."""
        # 1. Lazy-import the native stack so the OCR family imports even when it is absent (mirrors
        #    rapidocr): a missing package is surfaced as a clear, actionable error, never a bare
        #    ImportError deep in the graph.
        try:
            import pytesseract
            from PIL import Image
        except ImportError as error:
            raise RuntimeError(
                "Tesseract OCR requires the 'pytesseract' package and Pillow — install the worker "
                "dependency group."
            ) from error

        # 2. Decode the crop bytes into a PIL image, then run word-level OCR with the chosen language
        #    and page-segmentation mode. A missing binary / language pack is a deployment error, so
        #    surface it plainly (the worker image must ship tesseract-ocr + the tesseract-ocr-<lang>
        #    data packs).
        pil_image = Image.open(io.BytesIO(image))
        try:
            return pytesseract.image_to_data(
                pil_image,
                lang=lang,
                config=f"--psm {psm}",
                output_type=pytesseract.Output.DICT,
            )
        except pytesseract.TesseractNotFoundError as error:
            raise RuntimeError(
                "The 'tesseract' binary is not installed or not on PATH — add tesseract-ocr to the "
                "worker image."
            ) from error
        except pytesseract.TesseractError as error:
            raise RuntimeError(
                f"Tesseract failed (is the '{lang}' language pack installed?): {error}"
            ) from error

    @classmethod
    async def read(cls, image: bytes, lang: str, psm: int) -> dict[str, Any]:
        """
        Run local Tesseract OCR off the event loop and return the raw word-level data.

        Args:
            image (bytes): The crop to read.
            lang (str): Tesseract language code(s), '+'-joined for multi-language OCR.
            psm (int): Tesseract page-segmentation mode.

        Returns:
            dict[str, Any]: Tesseract's parallel-list data (``text`` words + their ``conf`` scores).
        """
        return await asyncio.to_thread(cls.__run_sync, image, lang, psm)

    @staticmethod
    def to_text(data: dict[str, Any]) -> tuple[str, float]:
        """
        Fold Tesseract's word-level data into the OCR node's contract: joined text + mean confidence.

        Tesseract reports a per-word ``conf`` in 0–100 (``-1`` for non-text layout tokens). This drops
        the ``-1`` / empty tokens, joins the surviving words with spaces, and normalizes the mean
        confidence into [0, 1].

        Args:
            data (dict[str, Any]): Tesseract's ``image_to_data`` DICT output.

        Returns:
            tuple[str, float]: The joined text and the mean per-word confidence (0.0 when empty).
        """
        # 1. Keep only real words with a valid confidence (Tesseract stamps -1 on layout tokens).
        words: list[str] = []
        confidences: list[float] = []
        for word, confidence in zip(data.get("text", []), data.get("conf", [])):
            text = (word or "").strip()
            score = float(confidence)
            if not text or score < 0:
                continue
            words.append(text)
            confidences.append(score)

        # 2. Nothing readable — an empty, zero-confidence reading (a ScoreBelow escalates on it).
        if not words:
            return "", 0.0

        # 3. Join the words and normalize the mean confidence from 0–100 to [0, 1].
        mean_confidence = sum(confidences) / len(confidences) / 100.0
        return " ".join(words), max(0.0, min(1.0, mean_confidence))


__all__ = ["TesseractEngine"]
