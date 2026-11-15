# ====== Code Summary ======
# InvalidInputError: raised when a request body cannot be decoded as the media type its route expects.

# ====== Standard Library Imports ======
from __future__ import annotations


class InvalidInputError(ValueError):
    """A client error (bad upload), NOT a server fault.

    `ServerErrorHandler` maps it to HTTP 422 with its message as the (clean, non-leaky) detail, so a
    malformed upload never reaches the model nor surfaces as an HTTP 500.
    """
