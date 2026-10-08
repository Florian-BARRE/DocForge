"""A 422 must never echo the submitted values: FastAPI's default puts each error's `input` (for a
missing field, the WHOLE body) in the response, so a malformed request would reflect its own secret."""


def test_422_keeps_the_shape_but_never_echoes_the_input(client) -> None:
    response = client.post(
        "/api/v1/collections",
        json={"name": "x", "pipeline": {"api_key": "sk-ECHO-SECRET-1"}, "bogus": 1},
    )

    assert response.status_code == 422
    assert "sk-ECHO-SECRET-1" not in response.text
    errors = response.json()["detail"]
    assert errors and all("input" not in error for error in errors)
    assert {"type", "loc", "msg"} <= set(errors[0])
    missing = {tuple(error["loc"]) for error in errors if error["type"] == "missing"}
    assert ("body", "supported_formats") in missing
