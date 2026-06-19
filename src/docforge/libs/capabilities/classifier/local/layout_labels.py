# ====== Code Summary ======
# Heuristic figure classifier using pixel statistics and parser label hints.
# No external model required — uses PIL grayscale analysis for scanned-text detection
# and maps known parser label strings directly to FigureKind.

from __future__ import annotations

import io

from loggerplusplus import LoggerClass

from libs.core.ir.models import FigureKind

from libs.capabilities.classifier.base import FigureClassifier, ClassificationResult
from typing import Any, ClassVar, Literal
from pydantic import BaseModel, Field, model_validator
from libs.capabilities._registry import register


class LayoutLabelsClassifier(FigureClassifier, LoggerClass):
    """
    Heuristic figure classifier combining label-hint mapping and pixel statistics.

    Config id: "layout_labels"

    Classification priority:
    1. Parser label hint (e.g. "chart", "diagram") → direct map, high confidence.
    2. Pixel grayscale statistics:
       - Very low contrast → DECORATIVE (uniform background: logo, separator).
       - Bimodal (dark + light pixels dominant) → SCANNED_TEXT.
       - Otherwise → PHOTO (VLM description adds retrieval value).

    No external model is required; runs on CPU with minimal overhead.
    Use VitOnnxClassifier for higher accuracy when a trained model is available.
    """

    name: str = "layout_labels"
    version: str = "1.0"

    # Grayscale std thresholds for the pixel heuristic
    _LOW_CONTRAST_STD: float = 30.0   # Below this → uniform → DECORATIVE
    _BIMODAL_RATIO: float = 0.70      # dark+light pixel fraction → SCANNED_TEXT

    # Known parser label → FigureKind (case-insensitive substring match)
    _LABEL_MAP: dict[str, FigureKind] = {
        "chart": FigureKind.CHART,
        "graph": FigureKind.CHART,
        "plot": FigureKind.CHART,
        "diagram": FigureKind.DIAGRAM,
        "schema": FigureKind.DIAGRAM,
        "flow": FigureKind.DIAGRAM,
        "picture": FigureKind.PHOTO,
        "photo": FigureKind.PHOTO,
        "image": FigureKind.PHOTO,
        "scan": FigureKind.SCANNED_TEXT,
        "scanned": FigureKind.SCANNED_TEXT,
        "logo": FigureKind.DECORATIVE,
        "icon": FigureKind.DECORATIVE,
        "decorative": FigureKind.DECORATIVE,
        "separator": FigureKind.DECORATIVE,
        "banner": FigureKind.DECORATIVE,
    }

    def __init__(self) -> None:
        """Initialize the layout-labels classifier."""
        LoggerClass.__init__(self)

    async def classify(
        self,
        img_bytes: bytes,
        label_hint: str | None = None,
    ) -> ClassificationResult:
        """
        Classify a figure image using label hints and/or pixel analysis.

        Args:
            img_bytes (bytes): PNG or JPEG image bytes of the figure crop.
            label_hint (str | None): Optional label from the parser's layout model.

        Returns:
            ClassificationResult: Predicted FigureKind with confidence score.
        """
        # 1. Try direct label-hint mapping (highest priority, lowest cost)
        if label_hint:
            hint_lower = label_hint.lower().strip()
            for keyword, kind in self._LABEL_MAP.items():
                if keyword in hint_lower:
                    self.logger.debug(
                        f"LayoutLabels: label_hint={label_hint!r} → {kind} (conf=0.90)"
                    )
                    return ClassificationResult(kind=kind, confidence=0.90)

        # 2. Fall back to pixel statistics
        kind, confidence = self._classify_by_pixels(img_bytes)
        self.logger.debug(
            f"LayoutLabels: heuristic → {kind} (conf={confidence:.2f})"
        )
        return ClassificationResult(kind=kind, confidence=confidence)

    def _classify_by_pixels(self, img_bytes: bytes) -> tuple[FigureKind, float]:
        """
        Analyse grayscale pixel statistics to estimate the figure kind.

        Returns a (FigureKind, confidence) tuple.  On any failure, returns PHOTO at 0.5.
        """
        try:
            from PIL import Image  # type: ignore
            import numpy as np  # type: ignore

            # 1. Convert to grayscale for statistics
            img = Image.open(io.BytesIO(img_bytes)).convert("L")
            pixels = np.array(img, dtype=np.float32)

            std = float(pixels.std())

            # 2. Very low contrast → uniform background → DECORATIVE
            if std < self._LOW_CONTRAST_STD:
                return FigureKind.DECORATIVE, 0.72

            # 3. Bimodal: majority pixels are near-black (<50) or near-white (>200)
            # Typical of scanned documents with dark text on bright paper
            dark_ratio = float((pixels < 50).mean())
            light_ratio = float((pixels > 200).mean())
            if (dark_ratio + light_ratio) > self._BIMODAL_RATIO:
                return FigureKind.SCANNED_TEXT, 0.68

            # 4. Default fallback: treat as PHOTO
            # VLM description will add retrieval value even if this is wrong
            return FigureKind.PHOTO, 0.55

        except Exception as exc:
            self.logger.warning(f"LayoutLabels pixel analysis failed: {exc}")
            return FigureKind.PHOTO, 0.50

# ─── Config ──────────────────────────────────────────────────────────────────



def _flatten_provider_spec(v: Any) -> Any:
    if isinstance(v, dict) and "params" in v and isinstance(v.get("params"), dict):
        return {"id": v.get("id"), **v["params"]}
    return v


@register("classifier")
class LayoutLabelsConfig(BaseModel):
    """
    Configuration for the heuristic layout-labels figure classifier.

    Config id: "layout_labels" — zero cost, always available, uses pixel stats + parser label hints.
    """

    _label: ClassVar[str] = "layout_labels — heuristic pixel-stats + parser-label classifier (cost=0)"
    _category: ClassVar[str] = "classifier"

    id: Literal["layout_labels"] = "layout_labels"

    @model_validator(mode="before")
    @classmethod
    def _compat(cls, v: Any) -> Any:
        return _flatten_provider_spec(v)

    def build(self) -> "LayoutLabelsClassifier":
        """Instantiate LayoutLabelsClassifier from this config."""
        return LayoutLabelsClassifier()

    def merge_defaults(self, cfg: Any) -> "LayoutLabelsConfig":
        return self

    @classmethod
    def availability(cls, cfg: Any) -> tuple[bool, str]:
        """Always available — zero-cost heuristic, no external deps."""
        return True, "Heuristic · cost=0 · always available"
