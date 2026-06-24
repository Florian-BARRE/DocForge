# ====== Code Summary ======
# Low-level async HTTP transport for the DocForge SDK: a single pooled httpx.AsyncClient,
# verb helpers rooted at the API's /api/v1 prefix, multipart upload, raw-bytes fetch, and
# uniform error raising. This is the ONLY place that talks to the network — every sub-API
# delegates here. It never imports the DocForge domain: it is a pure REST client.

from __future__ import annotations

# ====== Standard Library Imports ======
import pathlib
from typing import Any

# ====== Third-Party Library Imports ======
import httpx
from loggerplusplus import LoggerClass


class DocForgeTransport(LoggerClass):
    """
    Async HTTP transport rooted at a DocForge deployment's ``/api/v1`` prefix.

    Holds one persistent ``httpx.AsyncClient`` for connection pooling across all SDK calls.
    Every helper raises ``RuntimeError`` on a non-2xx response so sub-APIs can stay terse.
    """

    def __init__(self, base_url: str, timeout: float) -> None:
        """
        Initialise the transport and bind the versioned API root.

        Args:
            base_url (str): DocForge base URL, e.g. ``http://docforge:8000``.
            timeout (float): Per-request timeout in seconds.
        """
        LoggerClass.__init__(self)
        # Store the versioned API root used by every endpoint helper.
        self._api_v1: str = f"{base_url.rstrip('/')}/api/v1"
        # Persistent async client — pooled connections across tool calls.
        self._http: httpx.AsyncClient = httpx.AsyncClient(timeout=timeout)
        self.logger.info(f"DocForge SDK transport ready - base: {self._api_v1}")

    async def aclose(self) -> None:
        """Close the underlying HTTP client (call on shutdown)."""
        await self._http.aclose()

    async def get(self, path: str, params: dict[str, Any] | None = None) -> Any:
        """
        Perform a GET request returning parsed JSON.

        Args:
            path (str): Path relative to ``/api/v1`` (e.g. ``/collections/list``).
            params (dict | None): Optional query parameters (None values are dropped).

        Returns:
            Any: Parsed JSON body.
        """
        # 1. Issue the request, dropping query params left as None
        res = await self._http.get(f"{self._api_v1}{path}", params=self._clean(params))

        # 2. Validate and parse
        self._raise_for_status(res)
        return res.json()

    async def get_bytes(self, path: str, params: dict[str, Any] | None = None) -> bytes:
        """
        Perform a GET request returning the raw response body (for binary endpoints).

        Args:
            path (str): Path relative to ``/api/v1`` (e.g. a page screenshot endpoint).
            params (dict | None): Optional query parameters.

        Returns:
            bytes: Raw response content.
        """
        # 1. Issue the request
        res = await self._http.get(f"{self._api_v1}{path}", params=self._clean(params))

        # 2. Validate and return raw bytes
        self._raise_for_status(res)
        return res.content

    async def post(self, path: str, body: dict[str, Any] | None = None) -> Any:
        """
        Perform a POST request with a JSON body.

        Args:
            path (str): Path relative to ``/api/v1``.
            body (dict | None): JSON-serialisable request body.

        Returns:
            Any: Parsed JSON body, or ``{}`` for ``204 No Content``.
        """
        # 1. Issue the request
        res = await self._http.post(f"{self._api_v1}{path}", json=body or {})

        # 2. Validate, then handle the empty-body case
        self._raise_for_status(res)
        if res.status_code == 204:
            return {}
        return res.json()

    async def delete(self, path: str) -> Any:
        """
        Perform a DELETE request.

        Args:
            path (str): Path relative to ``/api/v1``.

        Returns:
            Any: Parsed JSON body, or ``{}`` for ``204 No Content``.
        """
        # 1. Issue the request
        res = await self._http.delete(f"{self._api_v1}{path}")

        # 2. Validate, then handle the empty-body case
        self._raise_for_status(res)
        if res.status_code == 204:
            return {}
        return res.json()

    async def upload(
        self, path: str, file_path: str, data: dict[str, Any] | None = None
    ) -> Any:
        """
        Upload a local file via multipart/form-data (field name ``file``).

        Args:
            path (str): Path relative to ``/api/v1`` (the ingest endpoint).
            file_path (str): Absolute path to the local file to upload.
            data (dict | None): Optional extra form fields (e.g. a ``metadata`` JSON string).

        Returns:
            Any: Parsed JSON body.

        Raises:
            FileNotFoundError: If ``file_path`` does not exist.
            ValueError: If ``file_path`` is not a regular file.
        """
        # 1. Validate the local path before touching the network
        local = pathlib.Path(file_path)
        if not local.exists():
            raise FileNotFoundError(f"File not found: {file_path}")
        if not local.is_file():
            raise ValueError(f"Path is not a file: {file_path}")

        # 2. Stream the file as multipart/form-data alongside any extra form fields
        with local.open("rb") as handle:
            res = await self._http.post(
                f"{self._api_v1}{path}",
                files={"file": (local.name, handle, "application/octet-stream")},
                data=data or {},
            )

        # 3. Validate and parse
        self._raise_for_status(res)
        return res.json()

    @staticmethod
    def _clean(params: dict[str, Any] | None) -> dict[str, Any] | None:
        """Drop keys whose value is None so they are not serialised as the string 'None'."""
        if not params:
            return None
        return {k: v for k, v in params.items() if v is not None}

    def _raise_for_status(self, res: httpx.Response) -> None:
        """Raise a RuntimeError carrying the status code and a truncated body on non-2xx."""
        if not res.is_success:
            raise RuntimeError(
                f"DocForge API error {res.status_code} on {res.request.method} "
                f"{res.request.url.path}: {res.text[:300]}"
            )
