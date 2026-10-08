# ====== Code Summary ======
# EmbedBaseline — the content-vector baseline (``collection.indexed_embed_signature``) split per AXIS.
# A rebuild copies dense vectors (it cannot re-embed them) but CAN re-encode the content sparse vector
# from the chunk text, so it must tell "the dense space moved" (reingest) from "only the sparse space
# moved" (rebuild re-encodes it). The signature is therefore ``<dense digest>:<sparse digest>`` (31 +
# 1 + 32 hex chars = the column's 64). A baseline stored before the split is one whole-space sha256:
# it still matches when the whole space is unchanged, and its dense half is recognised by re-hashing
# the current config under each plausible pre-switch sparse slot (EmbedVectorSpace.sparse_rewrites).

# ====== Standard Library Imports ======
import hashlib
import json

# ====== Local Project Imports ======
from .index_signature_embed import EmbedVectorSpace

# The separator of the per-axis signature (never in a hex digest, so a whole-space hash has none).
_SEPARATOR = ":"
# Hex chars kept per half so the composite fits the 64-char column.
_DENSE_CHARS = 31
_SPARSE_CHARS = 32
# The length of a slot node's canonical fingerprint tuple (an unknown kind's is shorter).
_SLOT_ENTRY_LEN = 6


class EmbedBaseline:
    """Static per-axis embed baseline: compute it, and compare a stored one per axis."""

    def __new__(cls, *args: object, **kwargs: object) -> None:
        raise TypeError("EmbedBaseline is a static-only class and cannot be instantiated.")

    @staticmethod
    def _digest(payload: object) -> str:
        """sha256 of the canonical JSON of a fingerprint (the pre-split embed-only format)."""
        return hashlib.sha256(json.dumps(payload, default=str).encode("utf-8")).hexdigest()

    @classmethod
    def _halves(cls, blob: dict) -> tuple[str, str]:
        """The (dense, sparse) digests of a blob's embed space.

        A slot node contributes ``(id, kind, dense slot, embed_semantic_fields)`` to the dense half and
        ``(id, kind, sparse slot, embed_lexical_fields)`` to the sparse half; a node of an unknown
        kind contributes its whole fingerprint to BOTH (any change moves both — conservative).
        """
        dense: list = []
        sparse: list = []
        for entry in EmbedVectorSpace.canonical(blob or {}):
            if len(entry) == _SLOT_ENTRY_LEN:
                dense.append((entry[0], entry[1], entry[2], entry[4]))
                sparse.append((entry[0], entry[1], entry[3], entry[5]))
            else:
                dense.append(entry)
                sparse.append(entry)
        return cls._digest(dense)[:_DENSE_CHARS], cls._digest(sparse)[:_SPARSE_CHARS]

    @classmethod
    def signature(cls, blob: dict) -> str:
        """
        The per-axis embed signature of a pipeline blob.

        Args:
            blob (dict): The collection's stored ingestion pipeline blob.

        Returns:
            str: ``<dense digest>:<sparse digest>`` (64 chars).
        """
        dense, sparse = cls._halves(blob)
        return f"{dense}{_SEPARATOR}{sparse}"

    @classmethod
    def whole_space_candidates(cls, blob: dict) -> set[str]:
        """Every PRE-split (whole-space) embed signature equivalent to the blob's embed space."""
        canonical = cls._digest(EmbedVectorSpace.canonical(blob or {}))
        legacy = EmbedVectorSpace.legacy_equivalents(blob or {})
        return {canonical} | {cls._digest(fingerprint) for fingerprint in legacy}

    @classmethod
    def candidates(cls, blob: dict) -> set[str]:
        """The per-axis signature plus every pre-split spelling of the same embed space."""
        return {cls.signature(blob)} | cls.whole_space_candidates(blob)

    @staticmethod
    def _split(stored: str) -> tuple[str, str] | None:
        """A per-axis stored signature's halves; None for a pre-split whole-space hash."""
        if _SEPARATOR not in stored:
            return None
        dense, _, sparse = stored.partition(_SEPARATOR)
        return dense, sparse

    @classmethod
    def dense_matches(cls, stored: str | None, blob: dict) -> bool:
        """
        Whether the dense vectors indexed under ``stored`` are in the blob's current dense space.

        Args:
            stored (str | None): The collection's ``indexed_embed_signature`` (None = unknown).
            blob (dict): The collection's current ingestion pipeline blob.

        Returns:
            bool: True when the dense half is unchanged (a pre-split baseline: unchanged whole space,
                or the current dense slot under a plausible former sparse slot). False when unknown.
        """
        if not stored:
            return False
        halves = cls._split(stored)
        if halves is not None:
            return halves[0] == cls._halves(blob)[0]
        if stored in cls.whole_space_candidates(blob):
            return True
        return any(
            stored in cls.whole_space_candidates(rewrite)
            for rewrite in EmbedVectorSpace.sparse_rewrites(blob)
        )

    @classmethod
    def sparse_matches(cls, stored: str | None, blob: dict) -> bool:
        """
        Whether the content sparse vectors indexed under ``stored`` are in the current sparse space.

        Args:
            stored (str | None): The collection's ``indexed_embed_signature`` (None = unknown).
            blob (dict): The collection's current ingestion pipeline blob.

        Returns:
            bool: True when the sparse half is unchanged (a pre-split baseline: only an unchanged
                whole space proves it). False when unknown.
        """
        if not stored:
            return False
        halves = cls._split(stored)
        if halves is not None:
            return halves[1] == cls._halves(blob)[1]
        return stored in cls.whole_space_candidates(blob)


__all__ = ["EmbedBaseline"]
