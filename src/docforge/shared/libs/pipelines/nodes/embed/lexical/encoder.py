# ====== Code Summary ======
# MetaLexicalEncoder — the local, provider-independent BM25 encoder of the METADATA lexical vectors
# (``meta_<slug>_bm25``). A metadata value (index side) becomes a sparse vector of BM25-saturated term
# frequencies; a query becomes a sparse vector of its unique terms at weight 1. Term ids are a stable
# 32-bit hash of the stemmed term (blake2b, so the vocabulary needs no fitting and never drifts).
# The IDF half of BM25 is NOT computed here: Qdrant applies it server-side through the
# ``Modifier.IDF`` the vector schema declares on every metadata sparse vector, so the score is
# Σ idf(t)·tf_bm25(t, value) over the query's terms. Pure code — no I/O, no model, no network.
#
# Versioning: this is encoding ``bm25_v1``. A collection's metadata sparse vectors are in this
# encoding iff Qdrant declares them with ``modifier=IDF`` (QdrantVectorSchema.is_bm25_meta); older
# collections hold BGE-M3 learned sparse weights there and keep the BGE query path until rebuilt.
# Any change to the analysis (stopwords, stemmers, folding) or to the hash is a NEW encoding.

# ====== Standard Library Imports ======
import hashlib
from collections import Counter

# ====== Internal Project Imports ======
from shared_libs.public_models.embed import SparseVector

# ====== Local Project Imports ======
from .analyzer import MetaLexicalAnalyzer

# BM25 term-frequency saturation (k1) and length normalisation (b) — the textbook Okapi defaults.
_K1 = 1.2
_B = 0.75
# Reference value length (tokens) for the length normalisation. A corpus average is unknowable to a
# per-value encoder, so a fixed reference stands in: metadata values are short names/titles, and a
# value longer than this is gently penalised against a shorter one matching the same terms.
_REFERENCE_LENGTH = 8.0
# Term ids are 4-byte hashes → the full uint32 range Qdrant sparse indices accept.
_HASH_BYTES = 4


class MetaLexicalEncoder:
    """Static BM25 sparse encoder for metadata values (index) and queries (search)."""

    ENCODING = "bm25_v1"

    def __new__(cls, *args: object, **kwargs: object) -> None:
        raise TypeError("MetaLexicalEncoder is a static-only class and cannot be instantiated.")

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
    def encode_value(cls, text: str) -> SparseVector:
        """
        Encode a metadata VALUE into its BM25 term-frequency vector (the index side).

        Args:
            text (str): The rendered metadata value.

        Returns:
            SparseVector: Indices sorted ascending; empty when the value has no content term.
        """
        # 1. Analyze → term frequencies + the value's token length.
        terms, length = MetaLexicalAnalyzer.analyze(text)
        frequencies = Counter(cls.term_id(term) for term in terms)
        # 2. BM25 saturation with length normalisation against the reference length.
        norm = _K1 * (1.0 - _B + _B * length / _REFERENCE_LENGTH)
        weights = {index: tf * (_K1 + 1.0) / (tf + norm) for index, tf in frequencies.items()}
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
        terms, _ = MetaLexicalAnalyzer.analyze(text)
        return cls.__sorted({cls.term_id(term): 1.0 for term in terms})

    @staticmethod
    def __sorted(weights: dict[int, float]) -> SparseVector:
        """Shape an index → weight map into a SparseVector with ascending indices."""
        indices = sorted(weights)
        return SparseVector(indices=indices, values=[weights[index] for index in indices])


__all__ = ["MetaLexicalEncoder"]
