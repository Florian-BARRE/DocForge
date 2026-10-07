"""A full-tier trace dump is persisted to SeaweedFS and served by the trace-payload endpoint, so a
provider secret carried in a node payload (a GenerationRequest endpoint api_key) must be masked."""

from pydantic import BaseModel

from shared_libs.pipelines.engine.trace import RecordTrace


class _Endpoint(BaseModel):
    base_url: str
    api_key: str


class _Request(BaseModel):
    prompt: str
    endpoint: _Endpoint
    targets: list[dict]


def test_full_dump_masks_nested_secrets_and_keeps_the_rest() -> None:
    request = _Request(
        prompt="p",
        endpoint=_Endpoint(base_url="http://llm", api_key="sk-TRACE-SECRET-1"),
        targets=[{"field": "summary", "api_key": "sk-TRACE-SECRET-2", "password": ""}],
    )

    dumped = RecordTrace.dump(request)

    assert "sk-TRACE-SECRET" not in repr(dumped)
    assert dumped["endpoint"] == {"base_url": "http://llm", "api_key": "__redacted__"}
    assert dumped["targets"][0] == {"field": "summary", "api_key": "__redacted__", "password": ""}
