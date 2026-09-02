# ====== Code Summary ======
# Normalizes a raw PaddleOCR.predict() result list (one `OCRResult`-like dict-like object per input
# image) into the sidecar's OCR-only contract: a single joined text string + one aggregate
# confidence. Verified against the paddleocr==3.7.0 / paddlex==3.7.0 wheel source (docs do not spell
# this shape out — see revision.py):
#
# - Each result exposes `res["rec_texts"]` (List[str], one entry per recognized text line) and
#   `res["rec_scores"]` (List[float], the matching per-line recognition confidences) — built in
#   paddlex.inference.pipelines.ocr.pipeline.predict(). A page with no text yields empty lists.
# - The reading text is the newline-join of every line; the aggregate confidence is the MEAN of the
#   per-line scores (0.0 when nothing was recognized) — the value a DocForge ScoreBelow transition
#   escalates on, mirroring how the worker's RapidOCR node averages its per-line confidences.
#
# This is the sidecar's ONLY paddle-free piece of OCR logic (imports nothing but `typing` +
# `loggerplusplus`), so it is unit-testable on an AVX-less CPU where PaddlePaddle itself SIGILLs.

# ====== Standard Library Imports ======
from typing import Any

# ====== Third-Party Library Imports ======
from loggerplusplus import loggerplusplus

logger = loggerplusplus.bind(identifier="PaddleOcrNormalizer")


class PaddleOcrResponseNormalizer:
    """
    Converts raw PaddleOCR per-image result objects into the sidecar's `POST /ocr` contract.

    Static-only helper (mirrors the sidecar's `PpStructureResponseNormalizer` convention) — never
    instantiated.
    """

    def __new__(cls, *args: Any, **kwargs: Any) -> "PaddleOcrResponseNormalizer":
        raise TypeError(f"{cls.__name__} is static-only and must not be instantiated.")

    @classmethod
    def to_reading(cls, results: list[Any]) -> dict[str, Any]:
        """
        Normalize a `PaddleOCR.predict()` result list into `{"text", "confidence"}`.

        Args:
            results (list[Any]): The list returned by `PaddleOCR.predict()` — one dict-like
                `OCRResult` per input image (a single image yields a one-element list). Each
                supports `res["rec_texts"]` / `res["rec_scores"]` item access.

        Returns:
            dict[str, Any]: `{"text": <newline-joined lines>, "confidence": <mean per-line score>}`;
                empty text and 0.0 confidence when nothing was recognized.
        """
        # 1. Collect every recognized line + its score across all page results (defensive: a
        #    malformed/partial result contributes nothing rather than crashing the whole read).
        lines: list[str] = []
        scores: list[float] = []
        for result in results:
            lines.extend(cls._texts(result))
            scores.extend(cls._scores(result))

        # 2. Join the lines and average the confidences — the single reading the contract returns.
        text = "\n".join(lines)
        confidence = sum(scores) / len(scores) if scores else 0.0
        return {"text": text, "confidence": confidence}

    @classmethod
    def _texts(cls, result: Any) -> list[str]:
        """The recognized text lines of one result (empty when the field is absent/None)."""
        raw = cls._get(result, "rec_texts") or []
        return [str(line) for line in raw]

    @classmethod
    def _scores(cls, result: Any) -> list[float]:
        """The per-line recognition confidences of one result (empty when absent/None)."""
        raw = cls._get(result, "rec_scores") or []
        return [float(score) for score in raw]

    @staticmethod
    def _get(obj: Any, key: str) -> Any:
        """
        Key-or-attribute access — the primary path is dict-like `OCRResult` item access
        (`res["rec_texts"]`); the attribute fallback guards a future PaddleX version exposing the
        fields as object attributes instead.

        Args:
            obj (Any): An `OCRResult`-like object or a dict.
            key (str): Field name to read.

        Returns:
            Any: The value, or None if present on neither shape.
        """
        try:
            return obj[key]
        except (KeyError, TypeError, IndexError):
            pass
        return getattr(obj, key, None)


__all__ = ["PaddleOcrResponseNormalizer"]
