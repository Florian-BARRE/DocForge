# ====== Code Summary ======
# Bm25Encoder — the pure BM25 sparse encoder behind the ``bm25_local`` sparse provider. An indexed
# text (a chunk body or a metadata value) becomes a sparse vector of BM25-saturated term frequencies;
# a query becomes a sparse vector of its unique terms at weight 1. Term ids are a stable 32-bit hash
# of the stemmed term (blake2b, so the vocabulary needs no fitting and never drifts). The IDF half of
# BM25 is NOT computed here: Qdrant applies it server-side through the ``Modifier.IDF`` the vector
# schema declares on every sparse vector of a collection whose sparse provider is bm25_local, so the
# score is Σ idf(t)·tf_bm25(t, text) over the query's terms. Pure code — no I/O, no model, no network.
#
# Versioning: this is encoding ``bm25_v1``. Any change to the analysis (stopwords, stemmers, folding)
# or to the hash is a NEW encoding (a new provider model id), never an in-place edit.

# ====== Standard Library Imports ======
import hashlib
from collections import Counter

# ====== Internal Project Imports ======
from shared_libs.public_models.embed import SparseVector

# ====== Local Project Imports ======
from .analyzer import Bm25Analyzer

# Term ids are 4-byte hashes → the full uint32 range Qdrant sparse indices accept.
_HASH_BYTES = 4


class Bm25Encoder:
    """Static BM25 sparse encoder for indexed texts (document side) and queries (search side)."""

    ENCODING = "bm25_v1"

    def __new__(cls, *args: object, **kwargs: object) -> None:
        raise TypeError("Bm25Encoder is a static-only class and cannot be instantiated.")

    @staticmethod
    def term_id(term: str) -> int:
        """
        The stable uint32 index of a stemmed term.

        Args:
            term (str): The stemmed term.

        Returns:
            int: Its 32-bit hash (identical across processes, hosts and Python versions).
        """
        digest = hashlib.blake2b(term.encode("utf-8"), digest_size=_HASH_BYTES).digest()
        return int.from_bytes(digest, "big")

    @classmethod
    def encode_document(
        cls, text: str, *, k1: float, b: float, reference_length: float
    ) -> SparseVector:
        """
        Encode an indexed text into its BM25 term-frequency vector (the index side).

        Args:
            text (str): The text to index (a chunk body or a rendered metadata value).
            k1 (float): BM25 term-frequency saturation.
            b (float): BM25 length normalisation strength.
            reference_length (float): The length (tokens) a text is normalised against — a per-text
                encoder cannot know the corpus average, so a fixed reference stands in.

        Returns:
            SparseVector: Indices sorted ascending; empty when the text has no content term.
        """
        # 1. Analyze → term frequencies + the text's token length.
        terms, length = Bm25Analyzer.analyze(text)
        frequencies = Counter(cls.term_id(term) for term in terms)
        # 2. BM25 saturation with length normalisation against the reference length.
        norm = k1 * (1.0 - b + b * length / reference_length)
        weights = {index: tf * (k1 + 1.0) / (tf + norm) for index, tf in frequencies.items()}
        return cls.__sorted(weights)

    @classmethod
    def encode_query(cls, text: str) -> SparseVector:
        """
        Encode a QUERY into its unique-term vector (weight 1 — Qdrant multiplies in the IDF).

        Args:
            text (str): The query text.

        Returns:
            SparseVector: Indices sorted ascending; empty when the query has no content term.
        """
        terms, _ = Bm25Analyzer.analyze(text)
        return cls.__sorted({cls.term_id(term): 1.0 for term in terms})

    @staticmethod
    def __sorted(weights: dict[int, float]) -> SparseVector:
        """Shape an index → weight map into a SparseVector with ascending indices."""
        indices = sorted(weights)
        return SparseVector(indices=indices, values=[weights[index] for index in indices])


__all__ = ["Bm25Encoder"]
