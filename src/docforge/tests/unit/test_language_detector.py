# ====== Code Summary ======
# Unit tests for LanguageDetector — offline ISO 639-1 detection with a confidence gate.

import pytest

from libs.providers.lang import LanguageDetector


@pytest.fixture
def detector() -> LanguageDetector:
    return LanguageDetector()


class TestLanguageDetector:
    def test_detects_french(self, detector: LanguageDetector) -> None:
        text = "Ceci est un document administratif rédigé en français pour les besoins du test."
        assert detector.detect(text) == "fr"

    def test_detects_english(self, detector: LanguageDetector) -> None:
        text = "This is an administrative document written in English for testing purposes."
        assert detector.detect(text) == "en"

    def test_empty_returns_none(self, detector: LanguageDetector) -> None:
        assert detector.detect("") is None
        assert detector.detect("   ") is None

    def test_too_short_returns_none(self, detector: LanguageDetector) -> None:
        # Below min_chars → unreliable → None (caller keeps its fallback)
        assert detector.detect("ok") is None

    def test_low_confidence_returns_none(self) -> None:
        # A high confidence floor rejects ambiguous input rather than guessing.
        strict = LanguageDetector(min_confidence=0.999, min_chars=1)
        assert strict.detect("12345 67890 !!! ???") is None
