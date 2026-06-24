# ====== Code Summary ======
# StaticBearerAuthMiddleware — a minimal ASGI middleware that gates the streamable-HTTP MCP app
# behind a single static bearer token. Used because the MCP port is exposed on the host; without
# it, anyone reaching the port could drive the document corpus. Built-in FastMCP auth is OAuth2-
# oriented and overkill for a shared-secret deployment.

from __future__ import annotations

# ====== Standard Library Imports ======
import hmac
from typing import Any

# ====== Third-Party Library Imports ======
from loggerplusplus import loggerplusplus
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse


class StaticBearerAuthMiddleware(BaseHTTPMiddleware):
    """
    Reject any request whose ``Authorization`` header is not ``Bearer <expected_token>``.

    The token is injected at construction (read from McpConfig) — never from the environment
    directly — so the middleware stays testable and the secret has a single source.
    """

    logger = loggerplusplus.bind(identifier="McpAuth")

    def __init__(self, app: Any, expected_token: str) -> None:
        """
        Store the expected bearer value.

        Args:
            app (Any): The wrapped ASGI application.
            expected_token (str): The shared secret clients must present.
        """
        super().__init__(app)
        self._expected_header = f"Bearer {expected_token}"

    async def dispatch(self, request: Request, call_next: Any) -> Any:
        """
        Compare the Authorization header in constant time and forward or reject.

        Args:
            request (Request): The incoming request.
            call_next (Any): The downstream handler.

        Returns:
            Any: A 401 JSON response on mismatch, otherwise the downstream response.
        """
        # 1. Constant-time comparison avoids leaking the token via timing
        provided = request.headers.get("authorization", "")
        if not hmac.compare_digest(provided, self._expected_header):
            self.logger.warning(f"Rejected unauthenticated request to {request.url.path}")
            return JSONResponse({"error": "unauthorized"}, status_code=401)

        # 2. Authorised — forward to the MCP app
        return await call_next(request)
