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

    def __init__(self, base_url: str, timeout: float, api_token: str = "") -> None:
        """
        Initialise the transport and bind the versioned API root.

        Args:
            base_url (str): DocForge base URL, e.g. ``http://docforge:8000``.
            timeout (float): Per-request timeout in seconds.
            api_token (str): Bearer token for the DocForge REST API. When non-empty,
                every outbound request carries ``Authorization: Bearer <token>``.
                Leave empty when calling a DocForge instance with ``AUTH_ENABLED=false``.
        """
        LoggerClass.__init__(self)
        # Store the bare root (for public, non-versioned routes like /health) and the
        # versioned API root used by every other endpoint helper.
        self._base_url: str = base_url.rstrip("/")
        self._api_v1: str = f"{self._base_url}/api/v1"
        # Build default headers — include the Authorization header only when a token is provided
        # so requests to an auth-disabled DocForge instance remain unaffected.
        _default_headers: dict[str, str] = {}
        if api_token:
            _default_headers["Authorization"] = f"Bearer {api_token}"
        # Persistent async client — pooled connections across tool calls.
        # Default headers are applied to every request (get/post/put/delete/upload/get_bytes).
        self._http: httpx.AsyncClient = httpx.AsyncClient(
            timeout=timeout,
            headers=_default_headers,
        )
        _auth_status = "with token" if api_token else "no auth"
        self.logger.info(f"DocForge SDK transport ready - base: {self._api_v1} ({_auth_status})")

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

    async def get_bytes(
        self, path: str, params: dict[str, Any] | None = None
    ) -> tuple[bytes, str]:
        """
        Perform a GET request returning the raw response body (for binary endpoints).

        Args:
            path (str): Path relative to ``/api/v1`` (e.g. the blob byte-stream endpoint).
            params (dict | None): Optional query parameters.

        Returns:
            tuple[bytes, str]: Raw response content and its registered content type.
        """
        # 1. Issue the request
        res = await self._http.get(f"{self._api_v1}{path}", params=self._clean(params))

        # 2. Validate and return raw bytes + the registered mime type
        self._raise_for_status(res)
        return res.content, res.headers.get("content-type", "application/octet-stream")

    async def get_public(self, path: str) -> Any:
        """
        Perform a GET request against a path NOT prefixed with ``/api/v1`` (the public health
        probe lives outside the authN-gated surface).

        Args:
            path (str): Path relative to the bare base URL (e.g. ``/health``).

        Returns:
            Any: Parsed JSON body.
        """
        # 1. Issue the request against the bare root, bypassing the /api/v1 prefix
        res = await self._http.get(f"{self._base_url}{path}")

        # 2. Validate and parse
        self._raise_for_status(res)
        return res.json()

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

    async def put(self, path: str, body: dict[str, Any] | None = None) -> Any:
        """
        Perform a PUT request with a JSON body.

        Args:
            path (str): Path relative to ``/api/v1``.
            body (dict | None): JSON-serialisable request body (sent as ``{}`` when None).

        Returns:
            Any: Parsed JSON body, or ``{}`` for ``204 No Content``.
        """
        # 1. Issue the request
        res = await self._http.put(f"{self._api_v1}{path}", json=body or {})

        # 2. Validate, then handle the empty-body case
        self._raise_for_status(res)
        if res.status_code == 204:
            return {}
        return res.json()

    async def patch(self, path: str, body: dict[str, Any] | None = None) -> Any:
        """
        Perform a PATCH request with a JSON body.

        Args:
            path (str): Path relative to ``/api/v1``.
            body (dict | None): JSON-serialisable request body (sent as ``{}`` when None).

        Returns:
            Any: Parsed JSON body, or ``{}`` for ``204 No Content``.
        """
        # 1. Issue the request
        res = await self._http.patch(f"{self._api_v1}{path}", json=body or {})

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
