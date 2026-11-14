# ====== Code Summary ======
# Records the HTTP request an SDK method produces, through the public client only. A catch-all respx
# route answers every call (the reply is ignored: this suite pins what goes OUT, the existing unit
# tests pin what comes back), and the request is reduced to a deterministic record: method, absolute
# URL (query included), the headers that are part of the contract, and the body. Multipart bodies keep
# their parts but lose the random boundary.

# ====== Standard Library Imports ======
import inspect
import json
import re
from typing import Any

# ====== Third-Party Library Imports ======
import httpx
import pydantic
import respx

# ====== Internal Project Imports ======
from docforge_sdk import AsyncClient, Client

# ====== Local Project Imports ======
from .wire_cases import WireCase

BASE = "http://wire.test"
TOKEN = "tok-wire"
_BOUNDARY = re.compile(r"boundary=([0-9a-fA-F]+)")
_KEPT_HEADERS = ("accept", "authorization", "content-type")


def reduce_request(request: httpx.Request) -> dict[str, Any]:
    """
    Reduce a sent request to a deterministic, JSON-serialisable record.

    Args:
        request (httpx.Request): The request the SDK sent.

    Returns:
        dict[str, Any]: method, url, kept headers, and the body (``json`` when the request is JSON,
        else ``body`` text with the multipart boundary replaced by a placeholder).
    """
    headers = {name: request.headers[name] for name in _KEPT_HEADERS if name in request.headers}
    content = request.content
    record: dict[str, Any] = {"method": request.method, "url": str(request.url)}

    # 1. The multipart boundary is random per request: name it, and keep the rest byte-for-byte.
    match = _BOUNDARY.search(headers.get("content-type", ""))
    if match:
        boundary = match.group(1)
        headers["content-type"] = headers["content-type"].replace(boundary, "BOUNDARY")
        content = content.replace(boundary.encode(), b"BOUNDARY")
    record["headers"] = headers

    # 2. A JSON body is recorded decoded (golden-friendly); the raw bytes are kept for the parity check.
    if not content:
        record["body"] = None
    elif headers.get("content-type", "").startswith("application/json"):
        record["json"] = json.loads(content)
    else:
        record["body"] = content.decode("utf-8", errors="replace")
    record["raw_body_bytes"] = len(content)
    return record


def raw_body(request: httpx.Request) -> bytes:
    """Return the request's raw bytes with any multipart boundary neutralised."""
    content = request.content
    match = _BOUNDARY.search(request.headers.get("content-type", ""))
    return content.replace(match.group(1).encode(), b"BOUNDARY") if match else content


def _drain(result: Any) -> list[Any]:
    """Consume a sync iterator result fully (a streaming download)."""
    return list(result)


async def record_async(case: WireCase) -> tuple[dict[str, Any], bytes]:
    """
    Run a case on the async client and return the request it produced.

    Args:
        case (WireCase): The call to make.

    Returns:
        tuple[dict[str, Any], bytes]: The reduced request record and its normalised raw body.
    """
    with respx.mock(assert_all_called=False) as router:
        router.route().mock(return_value=httpx.Response(200, json={}))
        async with AsyncClient(BASE, api_token=TOKEN) as client:
            method = getattr(getattr(client, case.resource), case.method)
            try:
                result = method(**case.make_kwargs())
                if inspect.isawaitable(result):
                    result = await result
                if case.drain:
                    _ = [chunk async for chunk in result]
            except pydantic.ValidationError:
                # The stub reply is not a valid model: only the outgoing request matters here. A
                # failure BEFORE any request left is a bad case, not a stub artefact.
                if not router.calls:
                    raise
        return _single(router, case)


def record_sync(case: WireCase) -> tuple[dict[str, Any], bytes]:
    """
    Run a case on the sync client and return the request it produced.

    Args:
        case (WireCase): The call to make.

    Returns:
        tuple[dict[str, Any], bytes]: The reduced request record and its normalised raw body.
    """
    with respx.mock(assert_all_called=False) as router:
        router.route().mock(return_value=httpx.Response(200, json={}))
        with Client(BASE, api_token=TOKEN) as client:
            method = getattr(getattr(client, case.resource), case.method)
            try:
                result = method(**case.make_kwargs())
                if case.drain:
                    _drain(result)
            except pydantic.ValidationError:
                # The stub reply is not a valid model: only the outgoing request matters here. A
                # failure BEFORE any request left is a bad case, not a stub artefact.
                if not router.calls:
                    raise
        return _single(router, case)


def _single(router: respx.MockRouter, case: WireCase) -> tuple[dict[str, Any], bytes]:
    """Return the one request the case sent (anything else is a contract change to look at)."""
    calls = router.calls
    assert len(calls) == 1, f"{case.case_id} sent {len(calls)} requests, expected exactly 1"
    request = calls[0].request
    return reduce_request(request), raw_body(request)
