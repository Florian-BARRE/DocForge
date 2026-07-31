# ====== Code Summary ======
# WebChromeClassifier — a conservative, format-agnostic detector of web-page CHROME: the navigation
# bars, menu runs and search-widget placeholders a real HTML page drags in alongside its content.
# Such blocks (e.g. "Contenus · Espaces · Il n'y a pas de résultat · Faire une recherche complète")
# are furniture, not prose, yet the parser emits them as ordinary text blocks that would otherwise
# be chunked and embedded. This flags only the CLEAR cases — a lone known placeholder phrase, or a
# short block that is a run of many tiny separator-split items (a menu bar) — so real prose is never
# demoted. The chunker maps a flagged block to a non-body role (kept, but not embedded, not a hit).

# ====== Standard Library Imports ======
import re

# ====== Internal Project Imports ======
from .helpers import ChunkerHelpers


class WebChromeClassifier:
    """Static, conservative classifier: is a block obvious web navigation/menu/search chrome?"""

    def __new__(cls, *args: object, **kwargs: object) -> None:
        raise TypeError("WebChromeClassifier is a static-only class and cannot be instantiated.")

    # Menu-item separators a nav bar / breadcrumb collapses into one text block. "/" is deliberately
    # EXCLUDED — dates (12/03/2024), paths and "and/or" would false-positive; the observed chrome
    # uses the interpunct/bullet/pipe family, which prose does not.
    _SEPARATOR = re.compile(r"[·•|›»∙‧・\t\n]+")

    # Normalized (lowercased, whitespace-collapsed) placeholder phrases that are pure UI, never
    # document prose. A block whose WHOLE (short) text is one of these — or a nav segment matching
    # one — is chrome. Kept exact-match and small on purpose (extend here); broader cookie/consent
    # banner detection is intentionally NOT attempted (too varied to demote safely).
    _CHROME_PHRASES = frozenset(
        {
            "no results",
            "no result",
            "no results found",
            "no matching results",
            "il n'y a pas de résultat",
            "il n'y a pas de résultats",
            "aucun résultat",
            "aucun resultat",
            "faire une recherche complète",
            "recherche complète",
            "search",
            "rechercher",
            "menu",
            "navigation",
            "skip to content",
            "aller au contenu",
            "back to top",
            "haut de page",
        }
    )

    # A nav bar is MANY tiny items; prose is not. Thresholds are deliberately strict.
    _MIN_SEGMENTS = 4  # a menu run has several items
    _MAX_WORDS_PER_SEGMENT = 4  # each nav label is short ("Espaces", "Applications")
    _FURNITURE_FRACTION = 0.75  # most items must look like labels, not sentences
    _MAX_TOTAL_WORDS = 40  # a nav/menu block is short overall — never a real paragraph

    @classmethod
    def is_chrome(cls, text: str | None) -> bool:
        """
        Whether a block's text is obvious web chrome (nav/menu run or a placeholder widget).

        Two conservative signals: (1) the whole short block IS a known chrome placeholder phrase;
        (2) the block splits on menu separators into MANY short, label-like segments — a menu bar
        or breadcrumb — while staying short overall. Anything else (a real paragraph, a single
        sentence, a long block) is left as body.

        Args:
            text (str | None): The block's native text.

        Returns:
            bool: True only for clear chrome; False for any real content.
        """
        if not text or not text.strip():
            return False
        normalized = ChunkerHelpers.normalize_text(text)

        # 1. A lone placeholder widget/label (a "Search" button, a "No results" line).
        if normalized in cls._CHROME_PHRASES:
            return True

        # 2. A menu/nav run: split on menu separators; a real paragraph yields a single segment and
        #    is never touched. Demote only when there are many short, label-like items in a short
        #    block — the shape of a nav bar, not of prose.
        segments = [segment for segment in cls._SEPARATOR.split(text) if segment.strip()]
        if len(segments) < cls._MIN_SEGMENTS:
            return False
        if len(normalized.split()) > cls._MAX_TOTAL_WORDS:
            return False
        furniture = sum(1 for segment in segments if cls.__is_label(segment))
        return furniture / len(segments) >= cls._FURNITURE_FRACTION

    @classmethod
    def __is_label(cls, segment: str) -> bool:
        """A nav-item-like segment: a very short run of words, or a known placeholder phrase."""
        normalized = ChunkerHelpers.normalize_text(segment)
        return (
            len(normalized.split()) <= cls._MAX_WORDS_PER_SEGMENT
            or normalized in cls._CHROME_PHRASES
        )


__all__ = ["WebChromeClassifier"]
