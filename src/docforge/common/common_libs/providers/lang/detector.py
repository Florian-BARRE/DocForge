# ====== Code Summary ======
# LanguageDetector — offline, deterministic language identification over parsed document text.
# Wraps py3langid (pure-Python, bundled model, no network) and returns an ISO 639-1 code only
# when the model is confident enough; otherwise None so the caller keeps a safe fallback.
# The trained model is loaded once per process and shared across detector instances.

# ====== Standard Library Imports ======
from __future__ import annotations

# ====== Third-Party Library Imports ======
from loggerplusplus import LoggerClass

# Process-wide cache of the loaded py3langid identifier (model load is non-trivial; do it once).
_IDENTIFIER = None


class LanguageDetector(LoggerClass):
    """
    Detect a document's dominant language from its text.

    Runs the py3langid model on a text sample and returns the predicted ISO 639-1 code when the
    normalized probability clears ``min_confidence``.  Short or low-confidence inputs return None
    so the caller can fall back (e.g. to the parser hint or ``"und"``) — language is never guessed.
    """

    def __init__(
        self,
        min_confidence: float = 0.5,
        min_chars: int = 20,
        max_chars: int = 4000,
    ) -> None:
        """
        Initialize the detector.

        Args:
            min_confidence (float): Minimum normalized probability [0, 1] to accept a prediction.
            min_chars (int): Below this many characters, detection is unreliable → None.
            max_chars (int): Only the first N characters are classified (speed; the head is enough).
        """
        LoggerClass.__init__(self)
        self._min_confidence = min_confidence
        self._min_chars = min_chars
        self._max_chars = max_chars

    def detect(self, text: str) -> str | None:
        """
        Detect the dominant language of a text sample.

        Args:
            text (str): Concatenated document text (already in reading order).

        Returns:
            str | None: ISO 639-1 code (e.g. ``"fr"``, ``"en"``) when confident, else None.
        """
        # 1. Too little signal to be reliable
        sample = (text or "").strip()
        if len(sample) < self._min_chars:
            return None

        # 2. Classify the head of the document (cheap and sufficient)
        try:
            lang, prob = self._identifier().classify(sample[: self._max_chars])
        except Exception as exc:  # never let detection break parsing
            self.logger.warning(f"LanguageDetector: detection failed ({exc})")
            return None

        # 3. Only accept a confident prediction
        if float(prob) < self._min_confidence:
            self.logger.debug(f"LanguageDetector: low confidence {float(prob):.2f} for {lang!r} → None")
            return None
        return str(lang)

    @staticmethod
    def _identifier():
        """Return the process-wide py3langid identifier, loading it once on first use."""
        global _IDENTIFIER
        if _IDENTIFIER is None:
            from py3langid.langid import MODEL_FILE, LanguageIdentifier

            # norm_probs=True → classify() returns a probability in [0, 1] usable as confidence.
            _IDENTIFIER = LanguageIdentifier.from_pickled_model(MODEL_FILE, norm_probs=True)
        return _IDENTIFIER
