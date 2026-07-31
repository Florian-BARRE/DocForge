# ====== Code Summary ======
# WebChromeClassifier — a conservative, format-agnostic detector of web-page CHROME: the navigation
# bars, menu runs, notification widgets and search-widget placeholders a real HTML page drags in
# alongside its content. Such blocks (e.g. "Contenus · Espaces · Il n'y a pas de résultat · Faire
# une recherche complète · Applications") are furniture, not prose, yet the parser emits them as
# ordinary text blocks that would otherwise be chunked and embedded. Two complementary signals flag
# them: (1) a PER-BLOCK signal for the clear cases — a known placeholder/search-widget phrase, or a
# block that splits on menu separators into many tiny labels (a nav bar collapsed into one block);
# (2) a RUN signal the projector applies across blocks — a stretch of several consecutive tiny
# label-like non-heading blocks is a menu/link list even when each item is its own block. A LONE
# short block is left as body (it may be a real short heading/value); only a real run is demoted.
# The chunker maps a flagged block to a non-body role (kept, inspectable, but never embedded / a hit).

# ====== Standard Library Imports ======
import re

# ====== Internal Project Imports ======
from .helpers import ChunkerHelpers

# Edge punctuation trimmed before an exact-phrase compare, so "Il n'y a pas de résultat." (a nav
# widget rendered with a trailing period) still matches the phrase list. Apostrophes are KEPT — they
# are internal to French elisions ("n'y") the phrases rely on.
_EDGE_PUNCTUATION = re.compile(r"^[^\wà-ÿ]+|[^\wà-ÿ']+$")


class WebChromeClassifier:
    """Static, conservative classifier: is a block obvious web navigation/menu/search chrome?"""

    def __new__(cls, *args: object, **kwargs: object) -> None:
        raise TypeError("WebChromeClassifier is a static-only class and cannot be instantiated.")

    # Menu-item separators a nav bar / breadcrumb collapses into one text block. "/" is deliberately
    # EXCLUDED — dates (12/03/2024), paths and "and/or" would false-positive; the observed chrome
    # uses the interpunct/bullet/pipe family, which prose does not.
    _SEPARATOR = re.compile(r"[·•|›»∙‧・\t\n]+")

    # Normalized (lowercased, whitespace-collapsed, edge-punctuation-trimmed) placeholder phrases
    # that are pure UI, never document prose. A block whose WHOLE (short) text is one of these — or a
    # nav segment matching one — is chrome. Kept exact-match and small on purpose (extend here);
    # broader cookie/consent banner detection is intentionally NOT attempted (too varied to demote).
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

    # Search-widget / breadcrumb PREFIXES: a SHORT block starting with one of these is a widget
    # placeholder ("Rechercher une application", "Search for a document"). Gated by a small word cap
    # so a real sentence merely opening with the word is never demoted. The trailing space anchors
    # a whole-word prefix ("rechercher " never matches "rechercherai").
    _CHROME_PREFIXES = (
        "rechercher ",
        "faire une recherche",
        "search for",
        "aller au ",
        "retour au ",
        "back to ",
        "skip to ",
    )
    _MAX_WIDGET_WORDS = 6

    # A nav bar collapsed into ONE block is MANY tiny items; prose is not. Thresholds stay strict.
    _MIN_SEGMENTS = 4  # a menu run has several items
    _MAX_WORDS_PER_SEGMENT = 4  # each nav label is short ("Espaces", "Applications")
    _FURNITURE_FRACTION = 0.75  # most items must look like labels, not sentences
    _MAX_TOTAL_WORDS = 40  # a nav/menu block is short overall — never a real paragraph

    # RUN signal: a stretch of at least this many consecutive tiny label-like blocks is a menu / link
    # list even when the parser emits each item as its own block. A label is a very short run of
    # words (or any per-block chrome). A LONE label is never demoted — only a real run is.
    MENU_RUN_MIN = 3
    _LABEL_MAX_WORDS = 4

    @classmethod
    def __phrase_key(cls, text: str) -> str:
        """Normalize + trim edge punctuation → the exact-match key used against the phrase list."""
        return _EDGE_PUNCTUATION.sub("", ChunkerHelpers.normalize_text(text))

    @classmethod
    def is_chrome(cls, text: str | None) -> bool:
        """
        Whether a block's text is obvious web chrome (nav/menu run or a placeholder widget).

        Three conservative PER-BLOCK signals: (1) the whole short block IS a known chrome placeholder
        phrase; (2) a short block STARTS WITH a known search-widget prefix; (3) the block splits on
        menu separators into MANY short, label-like segments — a menu bar collapsed into one block.
        Anything else (a real paragraph, a single sentence, a long block) is left as body.

        Args:
            text (str | None): The block's native text.

        Returns:
            bool: True only for clear per-block chrome; False for any real content.
        """
        if not text or not text.strip():
            return False
        key = cls.__phrase_key(text)

        # 1. A lone placeholder widget/label (a "Search" button, a "No results" line).
        if key in cls._CHROME_PHRASES:
            return True

        # 2. A short search-widget / breadcrumb placeholder ("Rechercher une application").
        if len(key.split()) <= cls._MAX_WIDGET_WORDS and key.startswith(cls._CHROME_PREFIXES):
            return True

        # 3. A menu/nav run collapsed into one block: split on menu separators; a real paragraph
        #    yields a single segment and is never touched. Demote only when there are many short,
        #    label-like items in a short block — the shape of a nav bar, not of prose.
        segments = [segment for segment in cls._SEPARATOR.split(text) if segment.strip()]
        if len(segments) < cls._MIN_SEGMENTS:
            return False
        if len(ChunkerHelpers.normalize_text(text).split()) > cls._MAX_TOTAL_WORDS:
            return False
        furniture = sum(1 for segment in segments if cls.__is_label(segment))
        return furniture / len(segments) >= cls._FURNITURE_FRACTION

    @classmethod
    def is_menu_label(cls, text: str | None) -> bool:
        """
        Whether a block is a single menu/link LABEL — a candidate item of a nav/menu run.

        A label is a very short run of words (a link caption like "Espaces", "Applications",
        "Rechercher une application") or any per-block chrome. Used ONLY by the run signal: a lone
        label is never demoted; several consecutive ones are. A blank block is not a label.

        Args:
            text (str | None): The block's native text.

        Returns:
            bool: True when the block could be one item of a menu / link list.
        """
        if not text or not text.strip():
            return False
        if cls.is_chrome(text):
            return True
        return 1 <= len(ChunkerHelpers.normalize_text(text).split()) <= cls._LABEL_MAX_WORDS

    @classmethod
    def __is_label(cls, segment: str) -> bool:
        """A nav-item-like segment: a very short run of words, or a known placeholder phrase."""
        normalized = ChunkerHelpers.normalize_text(segment)
        return (
            len(normalized.split()) <= cls._MAX_WORDS_PER_SEGMENT
            or cls.__phrase_key(segment) in cls._CHROME_PHRASES
        )


__all__ = ["WebChromeClassifier"]
