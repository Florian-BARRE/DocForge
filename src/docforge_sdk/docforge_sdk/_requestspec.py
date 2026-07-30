# ====== Code Summary ======
# The immutable description of a single HTTP call. A RequestSpec is pure data — it carries the method,
# API-relative path and payload, and performs no I/O. Resource classes build specs; transports execute
# them. Centralising URL/body shape here keeps it out of the async/sync transport bodies.

# ====== Standard Library Imports ======
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class RequestSpec:
    """
    An immutable, I/O-free description of one API request.

    The ``json`` and ``files`` payloads are typed ``Any`` because they are opaque, endpoint-shaped
    bodies already serialised by the calling resource (a model dump or an httpx multipart mapping).

    Attributes:
        method (str): The HTTP method (e.g. ``"GET"``, ``"POST"``, ``"DELETE"``).
        path (str): The path relative to the API root (e.g. ``"/auth/keys"``).
        params (dict[str, Any] | None): Query parameters; ``None`` values are dropped at execution.
        json (Any): The JSON request body, or ``None`` for bodyless requests.
        files (Any): The multipart file mapping for uploads, or ``None``.
    """

    method: str
    path: str
    params: dict[str, Any] | None = None
    json: Any = None
    files: Any = None


__all__ = ["RequestSpec"]
