# ====== Code Summary ======
# Bm25Analyzer — the pure text → terms analysis of the local BM25 sparse provider (bm25_local):
# lowercase → Unicode NFKD accent fold → tokenize on non-alphanumerics → French + English stopword
# removal → Snowball stemming. A text carries no language tag and the query side cannot
# know one either, so each token emits the UNION of its French and English stems (deduplicated):
# the analysis stays identical on both sides, a French word matches through its French stem and an
# English word through its English one. Deterministic, no I/O, no model download.

# ====== Standard Library Imports ======
import re
import unicodedata

# ====== Third-Party Library Imports ======
import snowballstemmer

# ====== Local Project Imports ======
from .stopwords import BM25_STOPWORDS

# NFKD leaves these ligatures/letters whole (no combining mark to strip), so they are spelled out.
_LIGATURES = str.maketrans({"œ": "oe", "æ": "ae", "ß": "ss", "ø": "o", "đ": "d", "ł": "l"})

# A token is a run of Unicode letters/digits — underscore excluded (``\w`` would keep it).
_TOKEN = re.compile(r"[^\W_]+")


class Bm25Analyzer:
    """Static, deterministic text analysis shared by the BM25 index and query encoders."""

    # Snowball stemmers are stateful objects; one per language, reused (analysis is synchronous).
    __STEMMERS = (snowballstemmer.stemmer("french"), snowballstemmer.stemmer("english"))

    def __new__(cls, *args: object, **kwargs: object) -> None:
        raise TypeError("Bm25Analyzer is a static-only class and cannot be instantiated.")

    @staticmethod
    def fold(text: str) -> str:
        """
        Lowercase and strip accents (NFKD + drop combining marks), spelling out ligatures.

        Args:
            text (str): The raw text.

        Returns:
            str: The folded text ("Exécution" → "execution", "Œuvre" → "oeuvre").
        """
        lowered = text.lower().translate(_LIGATURES)
        decomposed = unicodedata.normalize("NFKD", lowered)
        return "".join(char for char in decomposed if not unicodedata.combining(char))

    @classmethod
    def tokens(cls, text: str) -> list[str]:
        """
        Fold, tokenize and drop stopwords — the surface tokens before stemming.

        Args:
            text (str): The raw text.

        Returns:
            list[str]: The content tokens, in order (duplicates kept — they are term frequency).
        """
        return [token for token in _TOKEN.findall(cls.fold(text)) if token not in BM25_STOPWORDS]

    @classmethod
    def stems(cls, token: str) -> list[str]:
        """
        The deduplicated French + English Snowball stems of one folded token.

        Args:
            token (str): A folded, non-stopword token.

        Returns:
            list[str]: One stem when both languages agree, two otherwise (French first).
        """
        out: list[str] = []
        for stemmer in cls.__STEMMERS:
            stem = stemmer.stemWord(token)
            if stem and stem not in out:
                out.append(stem)
        return out

    @classmethod
    def analyze(cls, text: str) -> tuple[list[str], int]:
        """
        Analyze a text into its stemmed terms and its token length.

        Args:
            text (str): The raw text (an indexed text or a query).

        Returns:
            tuple[list[str], int]: Every emitted term (repeated per occurrence — term frequency)
                and the number of content tokens (the BM25 document length).
        """
        tokens = cls.tokens(text)
        terms = [stem for token in tokens for stem in cls.stems(token)]
        return terms, len(tokens)


__all__ = ["Bm25Analyzer"]
