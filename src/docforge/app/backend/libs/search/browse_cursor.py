# ====== Code Summary ======
# BrowseCursor — the opaque keyset cursor of the chunk browse. It encodes the LAST key of a page —
# (document_id, chunk_index, chunk_id), the browse's total order — as URL-safe base64 JSON. A keyset
# (not an offset, not a Qdrant point-id offset) is stable: the next page is "every match strictly
# after this key", so chunks ingested/deleted between two calls never shift, duplicate or skip the
# surviving ones, and the key stays meaningful even if the chunk it names was deleted meanwhile.

# ====== Standard Library Imports ======
import base64
import binascii
import json
from dataclasses import dataclass


class BrowseCursorError(ValueError):
    """Raised when a cursor string is not one this API issued (→ 422)."""


@dataclass(frozen=True, slots=True)
class BrowseCursor:
    """
    The position after which the next browse page starts.

    Attributes:
        document_id (str): The last returned chunk's document id.
        chunk_index (int): The last returned chunk's ordinal within its document.
        chunk_id (str): The last returned chunk's id (the tie-breaker of the total order).
    """

    document_id: str
    chunk_index: int
    chunk_id: str

    @classmethod
    def decode(cls, token: str) -> "BrowseCursor":
        """
        Parse an opaque cursor string.

        Args:
            token (str): The ``next_cursor`` of a previous page.

        Returns:
            BrowseCursor: The decoded position.

        Raises:
            BrowseCursorError: The token is not a cursor this API issued.
        """
        # 1. base64url → JSON → the three typed keys; anything else is a caller error.
        try:
            padded = token + "=" * (-len(token) % 4)
            data = json.loads(base64.urlsafe_b64decode(padded.encode()))
            return cls(str(data["d"]), int(data["i"]), str(data["c"]))
        except (binascii.Error, ValueError, KeyError, TypeError, UnicodeDecodeError) as exc:
            raise BrowseCursorError(
                f"invalid cursor {token!r} — pass a next_cursor as returned"
            ) from exc

    def encode(self) -> str:
        """
        Serialise the position as an opaque, URL-safe token.

        Returns:
            str: base64url (unpadded) of the compact JSON key.
        """
        # 1. Compact JSON keeps the token short; padding is stripped (re-added on decode).
        raw = json.dumps({"d": self.document_id, "i": self.chunk_index, "c": self.chunk_id})
        return base64.urlsafe_b64encode(raw.encode()).decode().rstrip("=")

    def key(self) -> tuple[str, int, str]:
        """The (document_id, chunk_index, chunk_id) keyset tuple the store pages after."""
        return (self.document_id, self.chunk_index, self.chunk_id)


__all__ = ["BrowseCursor", "BrowseCursorError"]
