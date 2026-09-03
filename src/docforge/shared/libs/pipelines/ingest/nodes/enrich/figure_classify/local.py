# ====== Code Summary ======
# LocalFigureClassifierHelpers — the fully-local, endpoint-free classification signal for the
# figure_classify node's ``local`` backend. It is a HEURISTIC classifier, NOT a trained model: it
# reads a crop's text density with the bundled RapidOCR (text covering most of the crop ⇒ a scanned
# text region) and then leans on best-effort visual statistics (whitespace + colour saturation via
# the OpenCV that already ships with RapidOCR) to separate charts / diagrams / photos, degrading
# safely to ``photo`` with a LOW score on ambiguity. Every decision emits a calibrated score so a
# ScoreBelow transition can still escalate the uncertain ones to a VLM when a collection wants it.
# It performs NO DB/S3 I/O — it only interprets the crop bytes and the OCR readings handed to it.

# ====== Standard Library Imports ======
from typing import Any

# ====== Third-Party Library Imports ======
from loggerplusplus import loggerplusplus

# ====== Internal Project Imports ======
from shared_libs.public_models import FigureKind

# ─── Calibrated confidences (honest: this is a heuristic, so nothing is asserted with certainty) ───
# A confident, text-dense crop reads as scanned_text — high but capped (never a trained certainty).
_SCANNED_SCORE = 0.75
# A class decided from visual statistics — moderate, so a ScoreBelow around 0.5+ can still escalate.
_VISUAL_SCORE = 0.5
# The safe degrade: an ambiguous crop becomes a photo (a generic caption is never wrong) at a LOW
# score, mirroring the VLM backend's own fallback so a ScoreBelow catches both paths identically.
_AMBIGUOUS_SCORE = 0.3

# ─── Heuristic thresholds (tuned conservatively; documented as best-effort, not learned) ───
_TEXT_COVERAGE_HIGH = 0.18  # fraction of the crop covered by confident text ⇒ scanned_text
_TEXT_COVERAGE_LOW = 0.03  # some text present (axis labels, legends) ⇒ lean chart
_TEXT_CONF_MIN = 0.45  # ignore very low-confidence reads when calling something scanned_text
_WHITESPACE_HIGH = 0.60  # mostly white ⇒ line art (chart / diagram) rather than a photo
_SATURATION_LOW = 0.18  # little colour ⇒ line art; rich colour ⇒ a photo
_SATURATION_HIGH = 0.35


class LocalFigureClassifierHelpers:
    """Static helpers for the local (endpoint-free) figure classification backend."""

    logger = loggerplusplus.bind(identifier="LocalFigureClassifierHelpers")

    def __new__(cls, *args: object, **kwargs: object) -> None:
        raise TypeError(
            "LocalFigureClassifierHelpers is a static-only class and cannot be instantiated."
        )

    @classmethod
    def coverage(cls, readings: list, dimensions: tuple[int, int] | None) -> float:
        """
        Estimate the fraction of the crop covered by detected text boxes.

        Args:
            readings (list): RapidOCR readings — each entry is ``[box, text, confidence]`` where
                ``box`` is four ``[x, y]`` corner points.
            dimensions (tuple[int, int] | None): The crop's ``(width, height)`` in pixels, or None
                when it could not be read (yields 0.0 coverage — the caller degrades safely).

        Returns:
            float: The summed box area over the crop area, clamped to ``[0, 1]`` (overlaps are not
            subtracted — this is a density signal, not an exact measure).
        """
        # 1. Without the crop dimensions there is no denominator — report no coverage.
        if dimensions is None:
            return 0.0
        width, height = dimensions
        area = float(width * height)
        if area <= 0.0:
            return 0.0
        # 2. Sum each detected box's polygon area (shoelace over its four corners).
        covered = sum(cls.__box_area(entry[0]) for entry in readings if entry and entry[0])
        return min(1.0, covered / area)

    @classmethod
    def decide(
        cls,
        text: str,
        confidence: float,
        coverage: float,
        image: bytes,
        config: Any,
    ) -> tuple[str, float]:
        """
        Classify a figure locally from its OCR density and best-effort visual statistics.

        Args:
            text (str): The OCR text read from the crop (unused directly; kept for future signals).
            confidence (float): The mean OCR confidence of the reading.
            coverage (float): The fraction of the crop covered by text (see ``coverage``).
            image (bytes): The crop bytes (decoded best-effort for whitespace / colour).
            config (Any): The classify config (reserved for future tunable thresholds).

        Returns:
            tuple[str, float]: A ``(FigureKind value, calibrated score)`` pair — degrades to
            ``photo`` at a LOW score on ambiguity so a ScoreBelow can escalate to a VLM.
        """
        _ = (text, config)
        # 1. Dense, confident text is the strongest local signal — a scanned text region.
        if coverage >= _TEXT_COVERAGE_HIGH and confidence >= _TEXT_CONF_MIN:
            return FigureKind.SCANNED_TEXT.value, _SCANNED_SCORE

        # 2. Separate the visual classes from best-effort whitespace + colour statistics.
        stats = cls.__visual_stats(image)
        if stats is not None:
            whitespace, saturation = stats
            # Mostly white, low-colour line art: a chart when it carries labels, else a diagram.
            if whitespace >= _WHITESPACE_HIGH and saturation <= _SATURATION_LOW:
                kind = (
                    FigureKind.CHART.value
                    if coverage >= _TEXT_COVERAGE_LOW
                    else FigureKind.DIAGRAM.value
                )
                return kind, _VISUAL_SCORE
            # Rich colour with little whitespace: a photograph or natural illustration.
            if saturation >= _SATURATION_HIGH:
                return FigureKind.PHOTO.value, _VISUAL_SCORE

        # 3. Some sparse text but no clear visual verdict — most likely a chart (axes + legend).
        if coverage >= _TEXT_COVERAGE_LOW:
            return FigureKind.CHART.value, _AMBIGUOUS_SCORE

        # 4. Ambiguous — degrade to a photo at a LOW score (a generic caption is never wrong).
        return FigureKind.PHOTO.value, _AMBIGUOUS_SCORE

    @staticmethod
    def __box_area(box: list) -> float:
        """Polygon area of a RapidOCR quad box via the shoelace formula (0.0 when malformed)."""
        # 1. A valid box is four [x, y] corners; anything else contributes nothing.
        if not box or len(box) < 3:
            return 0.0
        try:
            points = [(float(point[0]), float(point[1])) for point in box]
        except (TypeError, ValueError, IndexError):
            return 0.0
        # 2. Shoelace sum over the closed polygon.
        total = 0.0
        for (x1, y1), (x2, y2) in zip(points, points[1:] + points[:1], strict=True):
            total += x1 * y2 - x2 * y1
        return abs(total) / 2.0

    @classmethod
    def __visual_stats(cls, image: bytes) -> tuple[float, float] | None:
        """
        Best-effort whitespace fraction + mean colour saturation of the crop (None on any failure).

        Uses the OpenCV that already ships with RapidOCR — no new dependency and no model download.
        Any decode/import failure degrades to None so the caller falls back to the text signal alone.

        Args:
            image (bytes): The crop bytes.

        Returns:
            tuple[float, float] | None: ``(whitespace_fraction, mean_saturation)`` both in ``[0, 1]``,
            or None when the crop could not be decoded.
        """
        try:
            import cv2
            import numpy as np

            array = cv2.imdecode(np.frombuffer(image, np.uint8), cv2.IMREAD_COLOR)
            if array is None:
                return None
            # 1. Whitespace: fraction of near-white pixels (all channels above a high threshold).
            whitespace = float((array > 240).all(axis=2).mean())
            # 2. Colour richness: mean saturation of the HSV image, normalised to [0, 1].
            saturation = float(cv2.cvtColor(array, cv2.COLOR_BGR2HSV)[:, :, 1].mean()) / 255.0
            return whitespace, saturation
        except Exception as error:  # noqa: BLE001 — any decode/import failure degrades safely.
            cls.logger.debug(f"Visual stats unavailable, falling back to text signal: {error!r}")
            return None


__all__ = ["LocalFigureClassifierHelpers"]
