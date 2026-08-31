# ====== Code Summary ======
# The asynchronous HTTP transport (over httpx.AsyncClient). Inherits every pure helper from
# _TransportBase and supplies only the async I/O primitive (_send); spec execution, upload and raw
# byte fetch route through that single chokepoint, so no endpoint hand-rolls its own parsing.

# ====== Standard Library Imports ======
from collections.abc import AsyncIterator
from typing import Any

# ====== Third-Party Library Imports ======
import httpx

# ====== Local Project Imports ======
from ._exceptions import APIConnectionError, APITimeoutError
from ._requestspec import RequestSpec
from ._transport_base import T, _TransportBase


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
            spec.method,
            self._url(spec.path),
            params=self._clean(spec.params),
            json=spec.json,
            files=spec.files,
        )
        self._raise_for_status(response)
        return self._parse(response, model)

    async def request_bare(self, spec: RequestSpec, model: type[T]) -> T:
        """
        Execute a request spec against the BARE origin (outside ``/api/v1``) and parse it.

        Mirrors ``request`` but targets an un-versioned route (e.g. the public ``/health`` probe).

        Args:
            spec (RequestSpec): The request description (its path is origin-relative).
            model (type[T]): The target type to validate the response into.

        Returns:
            T: The validated response model.
        """
        response = await self._send(
            spec.method,
            self._bare_url(spec.path),
            params=self._clean(spec.params),
            json=spec.json,
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

    async def get_bytes_typed(self, path: str) -> tuple[bytes, str]:
        """
        Fetch a raw binary body together with its server-declared media type.

        Args:
            path (str): The API-relative path.

        Returns:
            tuple[bytes, str]: The raw content and its ``Content-Type`` (a generic octet-stream
            fallback when the header is absent).
        """
        response = await self._send("GET", self._url(path))
        self._raise_for_status(response)
        mime_type = response.headers.get("content-type", "application/octet-stream")
        return response.content, mime_type

    async def stream_get(self, path: str) -> AsyncIterator[bytes]:
        """
        Stream a GET response body in bounded chunks, never buffering it whole in memory.

        Bypasses ``_send`` (which returns a fully-read response) since httpx only streams the
        response body via its ``.stream()`` context manager; the same timeout/connection mapping is
        applied around it so callers see the same SDK exceptions either way.

        Args:
            path (str): The API-relative path.

        Yields:
            bytes: Successive chunks of the response body.

        Raises:
            APITimeoutError: When the request timed out.
            APIConnectionError: When the API could not be reached.
        """
        try:
            async with self._client.stream("GET", self._url(path)) as response:
                if response.status_code >= 400:
                    await response.aread()
                    self._raise_for_status(response)
                async for chunk in response.aiter_bytes():
                    yield chunk
        except httpx.TimeoutException as error:
            raise APITimeoutError(str(error)) from error
        except httpx.TransportError as error:
            raise APIConnectionError(str(error)) from error

    async def aclose(self) -> None:
        """Close the underlying httpx client and release its connections."""
        await self._client.aclose()


__all__ = ["AsyncTransport"]
