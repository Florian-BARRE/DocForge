# ====== Code Summary ======
# The single error raised when an edit operation cannot be realised against a blob — an unknown
# container path, an unknown node for a set_* op, a duplicate explicit id, or an unknown
# family/kind. It is DATA for the caller (the /edit endpoint turns it into a 200 response with
# edit_error set), never an HTTP 500: an impossible operation is a user mistake, not a server bug.


class EditError(Exception):
    """Raised when an edit operation is impossible to apply; carries a precise human message."""


__all__ = ["EditError"]
