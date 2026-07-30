# ====== Code Summary ======
# The public exception hierarchy for the SDK. Every failure a caller can catch descends from
# ``DocForgeError``. Transport-level failures (no connection, timeout) and HTTP error statuses map to
# dedicated subclasses so callers can branch on failure kind without inspecting raw httpx objects.

# ====== Standard Library Imports ======
from typing import Any

# ====== Third-Party Library Imports ======
import httpx


class DocForgeError(Exception):
    """Base class for every error raised by the DocForge SDK."""


class APIConnectionError(DocForgeError):
    """Raised when the API could not be reached (DNS, refused connection, network drop)."""


class APITimeoutError(APIConnectionError):
    """Raised when a request exceeded the configured timeout before a response arrived."""


class APIStatusError(DocForgeError):
    """
    Raised when the API returned a 4xx/5xx HTTP status.

    Attributes:
        status_code (int): The HTTP status code returned by the API.
        body (Any): The parsed response body (JSON when decodable, else raw text) — an opaque,
            server-shaped error payload.
    """

    def __init__(self, message: str, *, status_code: int, body: Any) -> None:
        """
        Initialize the status error with the failing code and response body.

        Args:
            message (str): Human-readable summary of the failure.
            status_code (int): The HTTP status code returned by the API.
            body (Any): The parsed response body (opaque server error payload).
        """
        super().__init__(message)
        self.status_code: int = status_code
        self.body: Any = body


class AuthError(APIStatusError):
    """Raised on 401 (unauthenticated) or 403 (unauthorized) responses."""


class NotFoundError(APIStatusError):
    """Raised on 404 responses (the target resource does not exist)."""


class ConflictError(APIStatusError):
    """Raised on 409 responses (the request conflicts with the resource's current state)."""


class UnprocessableError(APIStatusError):
    """Raised on 422 responses (the request body failed server-side validation)."""


# Maps an HTTP status code to the most specific exception class for it.
_STATUS_TO_EXCEPTION: dict[int, type[APIStatusError]] = {
    401: AuthError,
    403: AuthError,
    404: NotFoundError,
    409: ConflictError,
    422: UnprocessableError,
}


def exception_from_response(response: httpx.Response) -> APIStatusError:
    """
    Build the most specific ``APIStatusError`` for an errored HTTP response.

    Args:
        response (httpx.Response): The response whose status is 4xx/5xx.

    Returns:
        APIStatusError: A ``NotFoundError`` / ``AuthError`` / ``ConflictError`` /
        ``UnprocessableError`` when the status is recognised, else a plain ``APIStatusError``.
    """
    # 1. Decode the body as JSON when possible; fall back to raw text for non-JSON errors.
    try:
        body: Any = response.json()
    except ValueError:
        body = response.text

    # 2. Pick the dedicated subclass for this status, defaulting to the generic status error.
    exception_class = _STATUS_TO_EXCEPTION.get(response.status_code, APIStatusError)
    message = f"API request failed with status {response.status_code}"
    return exception_class(message, status_code=response.status_code, body=body)


__all__ = [
    "DocForgeError",
    "APIConnectionError",
    "APITimeoutError",
    "APIStatusError",
    "AuthError",
    "NotFoundError",
    "ConflictError",
    "UnprocessableError",
    "exception_from_response",
]
