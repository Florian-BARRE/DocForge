# ====== Code Summary ======
# Abstract base class + ClassificationResult for all figure classifier implementations.
# Classifiers route figures in S2: kind determines OCR / VLM / chart-to-data routing.

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

from ir.models import FigureKind


@dataclass(slots=True)
class ClassificationResult:
    """Output of a single figure classification call."""

    kind: FigureKind
    confidence: float  # [0.0, 1.0] — classifier certainty in the predicted kind

    def score(self) -> float | None:
        """ScoredResult — classifier escalation gates on the prediction confidence."""
        return self.confidence


class FigureClassifier(ABC):
    """
    Abstract base class for all figure classifiers.

    Classifiers route each figure to the appropriate S2 enrichment path:
    - SCANNED_TEXT → OCR only
    - CHART        → OCR + VLM description + chart-to-data
    - DIAGRAM      → OCR + VLM description
    - PHOTO        → VLM description only
    - DECORATIVE   → skip (no OCR, no VLM)

    Class attributes:
        name (str): Provider identifier used in logs.
        version (str): Classifier version string.
    """

    name: str
    version: str

    @abstractmethod
    async def classify(
        self,
        img_bytes: bytes,
        label_hint: str | None = None,
    ) -> ClassificationResult:
        """
        Classify a figure image into a FigureKind.

        Args:
            img_bytes (bytes): PNG or JPEG image bytes of the figure crop.
            label_hint (str | None): Optional layout-model label from the parser
                (e.g. \"chart\", \"diagram\") to bias the prediction without
                additional inference cost.

        Returns:
            ClassificationResult: Predicted FigureKind and confidence in [0, 1].
        """
        ...
