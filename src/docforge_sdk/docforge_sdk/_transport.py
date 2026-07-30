# ====== Code Summary ======
# The HTTP transports. Two classes — AsyncTransport (over httpx.AsyncClient) and SyncTransport (over
# httpx.Client) — share every piece of pure behaviour (URL building, header building, param cleaning,
# status→exception mapping, response parsing) via _TransportBase. Each concrete transport only supplies
# the I/O primitive (the httpx call); spec execution and response parsing are written ONCE per class
# with the target model passed in, so no endpoint ever hand-rolls its own parsing.

# ====== Standard Library Imports ======
from typing import Any, TypeVar

# ====== Third-Party Library Imports ======
import httpx
from pydantic import TypeAdapter

# ====== Local Project Imports ======
from ._exceptions import APIConnectionError, APITimeoutError, exception_from_response
from ._requestspec import RequestSpec

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


class AsyncTransport(_TransportBase):
    """Asynchronous transport backed by an ``httpx.AsyncClient``."""

    def __init__(self, base_url: str, timeout: float, api_token: str = "") -> None:
        """
        Create the underlying async httpx client with the resolved headers and timeout.

        Args:
            base_url (str): The API origin.
            timeout (float): Per-request timeout in seconds.
            api_token (str): Bearer token; empty means unauthenticated.
        """
        super().__init__(base_url, timeout, api_token)
        self._client = httpx.AsyncClient(timeout=timeout, headers=self._headers)

    async def _send(
        self,
        method: str,
        url: str,
        *,
        params: dict[str, Any] | None = None,
        json: Any = None,
        data: Any = None,
        files: Any = None,
    ) -> httpx.Response:
        """
        Execute a single httpx call, mapping transport failures to SDK exceptions.

        Args:
            method (str): The HTTP method.
            url (str): The absolute request URL.
            params (dict[str, Any] | None): Cleaned query parameters.
            json (Any): The JSON body, if any.
            data (Any): The form body for multipart uploads, if any.
            files (Any): The multipart file mapping, if any.

        Returns:
            httpx.Response: The raw response (status not yet checked).

        Raises:
            APITimeoutError: When the request timed out.
            APIConnectionError: When the API could not be reached.
        """
        # 1. A timeout is a specific connection failure — catch it before the broader transport error.
        try:
            return await self._client.request(
                method, url, params=params, json=json, data=data, files=files
            )
        except httpx.TimeoutException as error:
            raise APITimeoutError(str(error)) from error
        except httpx.TransportError as error:
            raise APIConnectionError(str(error)) from error

    async def request(self, spec: RequestSpec, model: type[T]) -> T:
        """
        Execute a request spec and validate its response into the target model.

        Args:
            spec (RequestSpec): The request description.
            model (type[T]): The target type to validate the response into.

        Returns:
            T: The validated response model.
        """
        # 1. Execute, 2. surface any error status, 3. parse — the single per-transport pipeline.
        response = await self._send(
            spec.method, self._url(spec.path), params=self._clean(spec.params), json=spec.json,
            files=spec.files,
        )
        self._raise_for_status(response)
        return self._parse(response, model)

    async def upload(self, path: str, files: Any, data: Any, model: type[T]) -> T:
        """
        Send a multipart upload and validate the response into the target model.

        Args:
            path (str): The API-relative path.
            files (Any): The multipart file mapping.
            data (Any): The accompanying form fields, if any.
            model (type[T]): The target response type.

        Returns:
            T: The validated response model.
        """
        response = await self._send("POST", self._url(path), files=files, data=data)
        self._raise_for_status(response)
        return self._parse(response, model)

    async def get_bytes(self, path: str) -> bytes:
        """
        Fetch a raw binary body (e.g. a stored blob) without JSON parsing.

        Args:
            path (str): The API-relative path.

        Returns:
            bytes: The raw response content.
        """
        response = await self._send("GET", self._url(path))
        self._raise_for_status(response)
        return response.content

    async def aclose(self) -> None:
        """Close the underlying httpx client and release its connections."""
        await self._client.aclose()


class SyncTransport(_TransportBase):
    """Synchronous transport backed by an ``httpx.Client``."""

    def __init__(self, base_url: str, timeout: float, api_token: str = "") -> None:
        """
        Create the underlying sync httpx client with the resolved headers and timeout.

        Args:
            base_url (str): The API origin.
            timeout (float): Per-request timeout in seconds.
            api_token (str): Bearer token; empty means unauthenticated.
        """
        super().__init__(base_url, timeout, api_token)
        self._client = httpx.Client(timeout=timeout, headers=self._headers)

    def _send(
        self,
        method: str,
        url: str,
        *,
        params: dict[str, Any] | None = None,
        json: Any = None,
        data: Any = None,
        files: Any = None,
    ) -> httpx.Response:
        """
        Execute a single httpx call, mapping transport failures to SDK exceptions.

        Args:
            method (str): The HTTP method.
            url (str): The absolute request URL.
            params (dict[str, Any] | None): Cleaned query parameters.
            json (Any): The JSON body, if any.
            data (Any): The form body for multipart uploads, if any.
            files (Any): The multipart file mapping, if any.

        Returns:
            httpx.Response: The raw response (status not yet checked).

        Raises:
            APITimeoutError: When the request timed out.
            APIConnectionError: When the API could not be reached.
        """
        # 1. A timeout is a specific connection failure — catch it before the broader transport error.
        try:
            return self._client.request(
                method, url, params=params, json=json, data=data, files=files
            )
        except httpx.TimeoutException as error:
            raise APITimeoutError(str(error)) from error
        except httpx.TransportError as error:
            raise APIConnectionError(str(error)) from error

    def request(self, spec: RequestSpec, model: type[T]) -> T:
        """
        Execute a request spec and validate its response into the target model.

        Args:
            spec (RequestSpec): The request description.
            model (type[T]): The target type to validate the response into.

        Returns:
            T: The validated response model.
        """
        # 1. Execute, 2. surface any error status, 3. parse — the single per-transport pipeline.
        response = self._send(
            spec.method, self._url(spec.path), params=self._clean(spec.params), json=spec.json,
            files=spec.files,
        )
        self._raise_for_status(response)
        return self._parse(response, model)

    def upload(self, path: str, files: Any, data: Any, model: type[T]) -> T:
        """
        Send a multipart upload and validate the response into the target model.

        Args:
            path (str): The API-relative path.
            files (Any): The multipart file mapping.
            data (Any): The accompanying form fields, if any.
            model (type[T]): The target response type.

        Returns:
            T: The validated response model.
        """
        response = self._send("POST", self._url(path), files=files, data=data)
        self._raise_for_status(response)
        return self._parse(response, model)

    def get_bytes(self, path: str) -> bytes:
        """
        Fetch a raw binary body (e.g. a stored blob) without JSON parsing.

        Args:
            path (str): The API-relative path.

        Returns:
            bytes: The raw response content.
        """
        response = self._send("GET", self._url(path))
        self._raise_for_status(response)
        return response.content

    def close(self) -> None:
        """Close the underlying httpx client and release its connections."""
        self._client.close()


__all__ = ["AsyncTransport", "SyncTransport"]
