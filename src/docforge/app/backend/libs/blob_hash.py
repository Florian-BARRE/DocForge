# ====== Code Summary ======
# BlobHasher — a stable content hash of a pipeline / search graph blob dict, used as an in-process
# cache key so that immutable per-blob work (graph build + validate, buildability) is paid once per
# distinct blob rather than on every request. The digest is order-independent (canonical JSON), so a
# blob whose keys are serialised in a different order still hits the same cache entry.

# ====== Standard Library Imports ======
import hashlib
import json
from typing import Any

# ====== Third-Party Library Imports ======
from loggerplusplus import loggerplusplus


class BlobHasher:
    """Static hasher producing a stable, order-independent digest of a blob dict (a cache key)."""

    logger = loggerplusplus.bind(identifier="BlobHasher")

    def __new__(cls, *args: object, **kwargs: object) -> None:
        raise TypeError("BlobHasher is a static-only class and cannot be instantiated.")

    @classmethod
    def digest(cls, blob: dict[str, Any]) -> str:
        """
        Return a stable sha256 hex digest of a blob dict.

        Args:
            blob (dict): The serialised blob (an ingest pipeline or a search graph).

        Returns:
            str: A hex digest stable across dict key ordering — the same blob content always maps to
                the same key. ``default=str`` keeps the dump total for any stray non-JSON scalar (a
                blob is plain JSON today, but a hash key must never raise on an unexpected value).
        """
        # 1. Canonicalise to order-independent, whitespace-free JSON, then hash it.
        canonical = json.dumps(blob, sort_keys=True, separators=(",", ":"), default=str)
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


__all__ = ["BlobHasher"]
