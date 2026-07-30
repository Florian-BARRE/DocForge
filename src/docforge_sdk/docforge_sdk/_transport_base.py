# ====== Code Summary ======
# The shared, I/O-free transport core. _TransportBase holds the resolved URL roots, the default
# headers and every pure helper (param cleaning, status→exception mapping, response parsing). The
# AsyncTransport and SyncTransport subclasses (in _transport_async / _transport_sync) inherit all of
# this and only supply the actual httpx call, so no endpoint ever hand-rolls its own parsing.

# ====== Standard Library Imports ======
from typing import Any, TypeVar

# ====== Third-Party Library Imports ======
import httpx
from pydantic import TypeAdapter

# ====== Local Project Imports ======
from ._exceptions import exception_from_response

# The type of the model a request is validated into (a BaseModel subclass, ``list[...]`` or ``None``).
T = TypeVar("T")

# The API version prefix every resource path is mounted under.
_API_PREFIX = "/api/v1"


class _TransportBase:
    """
    Shared, I/O-free behaviour for both transports.

    Holds the resolved URL roots, the default headers and the pure helpers (param cleaning, status
    mapping, response parsing) so the async and sync subclasses only differ by the actual httpx call.
    """

    def __init__(self, base_url: str, timeout: float, api_token: str = "") -> None:
        """
        Resolve the URL roots and build the default headers.

        Args:
            base_url (str): The API origin, e.g. ``"http://localhost:10040"``.
            timeout (float): Per-request timeout in seconds.
            api_token (str): Bearer token; when empty, no Authorization header is sent.
        """
        # 1. Keep both a bare origin (for un-versioned routes like /health) and the versioned root.
        self._root: str = base_url.rstrip("/")
        self._api_root: str = f"{self._root}{_API_PREFIX}"
        self._timeout: float = timeout
        self._headers: dict[str, str] = self._build_headers(api_token)

    @staticmethod
    def _build_headers(api_token: str) -> dict[str, str]:
        """
        Build the default request headers, adding Authorization only when a token is present.

        Args:
            api_token (str): The bearer token, possibly empty.

        Returns:
            dict[str, str]: The default headers for every request.
        """
        # 1. Always accept JSON; only attach the bearer credential when one was configured.
        headers = {"Accept": "application/json"}
        if api_token:
            headers["Authorization"] = f"Bearer {api_token}"
        return headers

    @staticmethod
    def _clean(params: dict[str, Any] | None) -> dict[str, Any] | None:
        """
        Drop ``None``-valued query parameters so they are never serialised into the URL.

        Args:
            params (dict[str, Any] | None): The raw query parameters.

        Returns:
            dict[str, Any] | None: The params without any ``None`` values, or ``None``.
        """
        # 1. Nothing to clean when no params were supplied.
        if params is None:
            return None
        return {key: value for key, value in params.items() if value is not None}

    def _url(self, path: str) -> str:
        """
        Build the absolute URL for an API-relative path.

        Args:
            path (str): The path relative to the API root (leading slash included).

        Returns:
            str: The fully-qualified request URL.
        """
        return f"{self._api_root}{path}"

    def _bare_url(self, path: str) -> str:
        """
        Build the absolute URL for a path mounted at the bare origin (outside ``/api/v1``).

        Used only by the public, un-versioned routes such as ``/health``.

        Args:
            path (str): The path relative to the origin (leading slash included).

        Returns:
            str: The fully-qualified request URL, without the API version prefix.
        """
        return f"{self._root}{path}"

    def _raise_for_status(self, response: httpx.Response) -> None:
        """
        Map any 4xx/5xx response to the matching SDK exception.

        Args:
            response (httpx.Response): The response to inspect.

        Raises:
            APIStatusError: (or a subclass) when the status code is >= 400.
        """
        # 1. Success statuses pass through untouched.
        if response.status_code >= 400:
            raise exception_from_response(response)

    def _parse(self, response: httpx.Response, model: type[T]) -> T:
        """
        Validate a response body into the target model.

        Args:
            response (httpx.Response): The successful response to parse.
            model (type[T]): The target type — a ``BaseModel`` subclass, a ``list[...]`` alias, or
                ``type(None)`` for bodyless (204) responses.

        Returns:
            T: The validated model instance (or ``None`` for a bodyless response).
        """
        # 1. A no-content endpoint (e.g. 204 on delete) has no body to validate. In this branch the
        #    target type is narrowed to ``None``, so returning None satisfies the declared T.
        if model is type(None):
            return None

        # 2. TypeAdapter handles single models AND ``list[...]`` aliases with one code path.
        return TypeAdapter(model).validate_python(response.json())


__all__ = ["T", "_TransportBase"]
