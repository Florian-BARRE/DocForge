# ====== Code Summary ======
# VectorNames — the stable naming of a collection's named vectors in Qdrant. The chunk body always
# has `content_dense` + `content_bm25`; each searchable metadata field gets `meta_<slug>_dense`
# (semantic) and/or `meta_<slug>_bm25` (lexical), where the slug is a deterministic sanitization of
# the field name — so the same field maps to the same vector name across reindexes.

# ====== Standard Library Imports ======
import re
import unicodedata


class VectorNames:
    """Static, deterministic naming of a collection's Qdrant named vectors."""

    CONTENT_DENSE = "content_dense"
    CONTENT_SPARSE = "content_bm25"

    def __new__(cls, *args: object, **kwargs: object) -> None:
        raise TypeError("VectorNames is a static-only class and cannot be instantiated.")

    @staticmethod
    def slug(field_name: str) -> str:
        """Sanitize a field name into a stable vector-name slug (lowercase ascii, [a-z0-9_])."""
        # Strip accents first (é → e) so French field names slug cleanly, then keep [a-z0-9].
        decomposed = unicodedata.normalize("NFKD", field_name.lower())
        ascii_only = "".join(char for char in decomposed if not unicodedata.combining(char))
        return re.sub(r"[^a-z0-9]+", "_", ascii_only).strip("_")

    @classmethod
    def field_dense(cls, field_name: str) -> str:
        """Named dense vector for a semantic metadata field."""
        return f"meta_{cls.slug(field_name)}_dense"

    @classmethod
    def field_sparse(cls, field_name: str) -> str:
        """Named sparse (BM25) vector for a lexical metadata field."""
        return f"meta_{cls.slug(field_name)}_bm25"


__all__ = ["VectorNames"]
