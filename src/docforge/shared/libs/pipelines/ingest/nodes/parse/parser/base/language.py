# ====== Code Summary ======
# LanguageDetector — a lightweight, dependency-free language identifier run at PARSE time, so the
# canonical DocumentIR carries a NORMALIZED ISO 639-1 code ("fr"/"en"/…) derived from the actual
# extracted text rather than an unreliable parser hint or a free-text LLM guess. It scores the text
# against small, distinctive stop-word sets per supported language and picks the best match; too
# little signal (empty/undetectable text) yields "" so the caller can fall back. No heavy model or
# extra package is pulled in — the corpus is FR/EN-centric and this stays conservative and cheap.

# ====== Standard Library Imports ======
import re

# Word tokenizer: runs of letters (incl. accented) and the apostrophe (French elisions: l', d', qu').
_WORD = re.compile(r"[a-zà-ÿ']+")

# At most this many leading words are scored — enough signal for a confident call, bounded cost on a
# long document (a language is dominant from its first paragraphs).
_MAX_WORDS = 400


class LanguageDetector:
    """Static stop-word-frequency language identifier → ISO 639-1 code (or "" when undetectable)."""

    def __new__(cls, *args: object, **kwargs: object) -> None:
        raise TypeError("LanguageDetector is a static-only class and cannot be instantiated.")

    # Small, DISTINCTIVE stop-word sets per language — the high-frequency function words that carry
    # the language signal. Kept intentionally compact (extend by adding a language here); the set of
    # supported languages is the FR/EN-centric corpus plus its common European neighbours so a
    # mixed-language document still resolves to a real code rather than a wrong one.
    _STOPWORDS: dict[str, frozenset[str]] = {
        "en": frozenset(
            {
                "the",
                "and",
                "of",
                "to",
                "in",
                "is",
                "that",
                "for",
                "it",
                "with",
                "as",
                "was",
                "are",
                "be",
                "this",
                "have",
                "or",
                "at",
                "by",
                "not",
                "from",
                "an",
                "which",
                "you",
                "we",
                "they",
                "there",
                "their",
                "would",
                "should",
                "can",
                "will",
                "has",
                "but",
            }
        ),
        "fr": frozenset(
            {
                "le",
                "la",
                "les",
                "de",
                "des",
                "un",
                "une",
                "et",
                "est",
                "dans",
                "que",
                "qui",
                "pour",
                "pas",
                "ne",
                "sur",
                "se",
                "ce",
                "il",
                "elle",
                "nous",
                "vous",
                "avec",
                "au",
                "aux",
                "du",
                "plus",
                "par",
                "sont",
                "être",
                "cette",
                "ces",
                "mais",
                "ou",
                "comme",
                "leur",
                "aussi",
                "sans",
                "sa",
                "son",
                "ses",
            }
        ),
        "es": frozenset(
            {
                "el",
                "la",
                "los",
                "las",
                "de",
                "un",
                "una",
                "y",
                "es",
                "en",
                "que",
                "por",
                "con",
                "para",
                "no",
                "se",
                "su",
                "lo",
                "como",
                "más",
                "pero",
                "sus",
                "del",
                "al",
                "este",
                "esta",
                "son",
                "entre",
                "cuando",
                "también",
            }
        ),
        "de": frozenset(
            {
                "der",
                "die",
                "das",
                "und",
                "ist",
                "ein",
                "eine",
                "den",
                "dem",
                "zu",
                "mit",
                "auf",
                "für",
                "nicht",
                "von",
                "im",
                "sich",
                "auch",
                "werden",
                "sind",
                "wird",
                "eines",
                "einer",
                "aber",
                "oder",
                "als",
                "wenn",
                "durch",
            }
        ),
        "it": frozenset(
            {
                "il",
                "lo",
                "la",
                "le",
                "di",
                "un",
                "una",
                "che",
                "per",
                "con",
                "non",
                "si",
                "come",
                "più",
                "sono",
                "del",
                "della",
                "gli",
                "nel",
                "alla",
                "anche",
                "questo",
                "questa",
                "ma",
                "oppure",
                "loro",
                "essere",
            }
        ),
        "pt": frozenset(
            {
                "o",
                "os",
                "as",
                "de",
                "um",
                "uma",
                "que",
                "por",
                "com",
                "para",
                "não",
                "se",
                "seu",
                "sua",
                "mais",
                "do",
                "da",
                "dos",
                "das",
                "este",
                "esta",
                "são",
                "quando",
                "também",
                "pelo",
                "pela",
                "como",
            }
        ),
    }

    # Minimum share of stop-word hits among scored words to trust a call — below it the text is too
    # sparse or off-language to name confidently, and "" (unknown) is returned.
    _MIN_RATIO = 0.05

    @classmethod
    def detect(cls, text: str | None) -> str:
        """
        Detect the dominant language of a text as an ISO 639-1 code.

        Scores the leading words against each language's distinctive stop-word set and returns the
        best-matching code. Returns "" when there is too little signal (empty text, or a match share
        below the confidence floor), so the caller can fall back to another hint.

        Args:
            text (str | None): The text to identify (document body, any length).

        Returns:
            str: The ISO 639-1 code of the dominant language, or "" when undetectable.
        """
        if not text or not text.strip():
            return ""
        words = _WORD.findall(text.lower())[:_MAX_WORDS]
        if not words:
            return ""
        # Count stop-word hits per language over the scored words.
        best_code = ""
        best_hits = 0
        for code, stopwords in cls._STOPWORDS.items():
            hits = sum(1 for word in words if word in stopwords)
            if hits > best_hits:
                best_code, best_hits = code, hits
        # Confidence floor: enough of the text must be recognised function words to trust the call.
        if best_hits / len(words) < cls._MIN_RATIO:
            return ""
        return best_code


__all__ = ["LanguageDetector"]
