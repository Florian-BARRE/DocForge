"""CORS exposes the API's custom response headers — without ``expose_headers`` a cross-origin browser
can't read ``X-Total-Count`` (the chunk-list total) and the other non-safelisted headers."""


def _allowed_origin() -> str:
    from config import RUNTIME_CONFIG  # noqa: PLC0415 — deferred until app/ is on sys.path

    origins = [
        o.strip() for o in RUNTIME_CONFIG.FASTAPI_CORS_ALLOWED_ORIGINS.split(",") if o.strip()
    ]
    return "http://localhost:10046" if "*" in origins or not origins else origins[0]


def test_cross_origin_response_exposes_x_total_count(client) -> None:
    response = client.get("/api/v1/pipelines", headers={"Origin": _allowed_origin()})

    assert response.status_code == 200
    exposed = {
        h.strip().lower() for h in response.headers["access-control-expose-headers"].split(",")
    }
    assert "x-total-count" in exposed
    assert {"x-request-id", "idempotency-replayed", "retry-after", "content-disposition"} <= exposed


def test_expose_list_names_x_total_count(fastapi_app) -> None:
    from entrypoint import CORS_EXPOSE_HEADERS  # noqa: PLC0415

    assert "X-Total-Count" in CORS_EXPOSE_HEADERS
