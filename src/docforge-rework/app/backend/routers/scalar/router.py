# ====== Code Summary ======
# Route serving the Scalar API-reference UI — a single HTML page loading the Scalar viewer from
# its CDN against this app's /openapi.json. No extra Python dependency.

# ====== Third-Party Library Imports ======
from fastapi import APIRouter
from fastapi.responses import HTMLResponse

# ====== Local Project Imports ======
from ...context import CONTEXT
from ...utils.error_handling import auto_handle_errors

router = APIRouter()


@router.get("", include_in_schema=False, response_class=HTMLResponse)
@auto_handle_errors
async def scalar_ui() -> HTMLResponse:
    """
    Serve the Scalar API-reference page.

    Returns:
        HTMLResponse: The viewer page, pointed at this app's OpenAPI document.
    """
    # 1. One static page: the Scalar viewer reads /openapi.json client-side.
    return HTMLResponse(
        content=f"""<!doctype html>
<html>
    <head>
        <title>{CONTEXT.RUNTIME_CONFIG.FASTAPI_APP_NAME} — API Reference</title>
        <meta charset="utf-8"/>
    </head>
    <body>
        <script id="api-reference" data-url="/openapi.json"></script>
        <script src="https://cdn.jsdelivr.net/npm/@scalar/api-reference"></script>
    </body>
</html>"""
    )


__all__ = ["router"]
