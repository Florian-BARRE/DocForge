"""Structgen capability: the field types force the schema, every returned value is strictly coerced
to its contract type (parity with metagen's old _generate+coerce), the endpoint is dual-sourced (a
step override wins, else the request's own), and the node is NOT scored.

The model call is faked exactly as test_metagen_stage.py fakes _generate — the coercion path is real.
"""

from shared_libs.pipelines.nodes.structgen.base import (
    StructGenConfig,
    StructGenConsumes,
    StructGenHelpers,
)
from shared_libs.pipelines.nodes.structgen.openai_compatible.core import (
    StructGenOpenAICompatibleNode,
)
from shared_libs.pipelines.registry import NodeRegistry
from shared_libs.public_models import (
    FieldOrigin,
    FieldScope,
    FieldType,
    GenerationField,
    GenerationRequest,
    MetadataFieldSpec,
    OpenAICompatConfig,
)


def _field(
    name: str, field_type: FieldType, enum_values: list[str] | None = None
) -> GenerationField:
    spec = MetadataFieldSpec(
        field_name=name,
        field_type=field_type,
        origin=FieldOrigin.GENERATED,
        scope=FieldScope.DOCUMENT,
        enum_values=enum_values,
    )
    return GenerationField(spec=spec, instruction=f"Fill {name}.")


FIELDS = [
    _field("summary", FieldType.STRING),
    _field("year", FieldType.INTEGER),
    _field("published_at", FieldType.DATETIME),
    _field("keywords", FieldType.KEYWORD_LIST),
    _field("relevance", FieldType.FLOAT),
    _field("flag", FieldType.BOOL),
    _field("category", FieldType.ENUM, enum_values=["science", "history"]),
    _field("missing", FieldType.STRING),
]

# Canned raw model answers per field (pre-coercion) — the per-type coercion cases.
ANSWERS: dict[str, object] = {
    "summary": "  A report about cats and bonds. ",  # str -> stripped
    "year": "2024",  # str -> int
    "published_at": "2024-03-01T10:00:00",  # ISO datetime, normalised
    "keywords": ["cats", " bonds ", ""],  # cleaned list
    "relevance": "not-a-number",  # uncoercible float -> dropped
    "flag": "true",  # str -> bool
    "category": "science",  # enum passthrough
    "missing": None,  # honest null -> absent
}


def _request(endpoint: OpenAICompatConfig, chunk_id: str | None = "d#c0") -> GenerationRequest:
    return GenerationRequest(
        request_id="r0",
        chunk_id=chunk_id,
        system_prompt="Extract metadata.",
        text="Cats purr softly. Bonds fell sharply.",
        fields=FIELDS,
        endpoint=endpoint,
        temperature=0.0,
        max_tokens=256,
    )


@NodeRegistry.register("structgen")
class FakeStructGenNode(StructGenOpenAICompatibleNode):
    """Records the call and returns canned answers instead of hitting an endpoint."""

    KIND = "test_structgen_fake"
    NAME = "F"
    SUMMARY = "t"

    def __init__(self, *args: object, **kwargs: object) -> None:
        super().__init__(*args, **kwargs)
        self.calls: list[tuple[tuple[str, ...], OpenAICompatConfig, GenerationRequest]] = []

    async def _generate(self, schema, request, endpoint):
        self.calls.append((tuple(schema["properties"]), endpoint, request))
        return {name: ANSWERS.get(name) for name in schema["properties"]}


async def test_structured_output_is_strictly_coerced_per_type() -> None:
    request = _request(OpenAICompatConfig(base_url="http://req", model="m-req"))
    node = FakeStructGenNode(id="s", config=StructGenConfig())

    out = await node.run(StructGenConsumes(request=request))

    # Every requested field went through the schema (one property per field, in order).
    assert node.calls[0][0] == (
        "summary",
        "year",
        "published_at",
        "keywords",
        "relevance",
        "flag",
        "category",
        "missing",
    )
    # Strict per-type coercion; uncoercible float and honest null are absent (never wrong-typed).
    assert out.values.values == {
        "summary": "A report about cats and bonds.",
        "year": 2024,
        "published_at": "2024-03-01T10:00:00",
        "keywords": ["cats", "bonds"],
        "flag": True,
        "category": "science",
    }
    # The result is carried back keyed to its source.
    assert out.values.request_id == "r0"
    assert out.values.chunk_id == "d#c0"


async def test_coercion_matches_the_helper_for_the_same_answers() -> None:
    """Parity: the node's values equal StructGenHelpers.coerce applied field-by-field."""
    request = _request(OpenAICompatConfig(base_url="http://req", model="m-req"))
    node = FakeStructGenNode(id="s", config=StructGenConfig())

    out = await node.run(StructGenConsumes(request=request))

    expected = {
        f.spec.field_name: coerced
        for f in FIELDS
        if (coerced := StructGenHelpers.coerce(ANSWERS.get(f.spec.field_name), f.spec.field_type))
        is not None
    }
    assert out.values.values == expected


async def test_empty_config_uses_the_request_endpoint() -> None:
    request = _request(
        OpenAICompatConfig(base_url="http://req", model="m-req", timeout_seconds=17.0)
    )
    node = FakeStructGenNode(id="s", config=StructGenConfig())

    await node.run(StructGenConsumes(request=request))

    _props, endpoint, _req = node.calls[0]
    assert endpoint.base_url == "http://req"
    assert endpoint.model == "m-req"
    assert endpoint.timeout_seconds == 17.0


async def test_step_override_wins_over_the_request_endpoint() -> None:
    request = _request(
        OpenAICompatConfig(base_url="http://req", model="m-req", timeout_seconds=17.0)
    )
    override = StructGenConfig(base_url="http://fallback", api_key="k", model="m-robust")
    node = FakeStructGenNode(id="s", config=override)

    await node.run(StructGenConsumes(request=request))

    _props, endpoint, _req = node.calls[0]
    assert endpoint.base_url == "http://fallback"
    assert endpoint.model == "m-robust"
    assert endpoint.api_key == "k"
    # Timeout was not overridden (config 0.0) — it inherits the request's.
    assert endpoint.timeout_seconds == 17.0


async def test_partial_override_is_resolved_per_field() -> None:
    """A step overriding ONLY base_url keeps the request's model/key/timeout — not dropped."""
    request = _request(
        OpenAICompatConfig(
            base_url="http://req", api_key="req-key", model="m-req", timeout_seconds=17.0
        )
    )
    node = FakeStructGenNode(id="s", config=StructGenConfig(base_url="http://fallback"))

    await node.run(StructGenConsumes(request=request))

    _props, endpoint, _req = node.calls[0]
    assert endpoint.base_url == "http://fallback"  # the one override wins
    assert endpoint.model == "m-req"  # inherited per-field, not silently dropped
    assert endpoint.api_key == "req-key"
    assert endpoint.timeout_seconds == 17.0


def test_out_of_enum_value_is_dropped() -> None:
    """An ENUM value the model invents (outside the whitelist) is dropped, never stored wrong."""
    # 1. Out-of-whitelist -> dropped.
    assert StructGenHelpers.coerce("sports", FieldType.ENUM, ["science", "history"]) is None
    # 2. A member survives, normalised to the DECLARED casing (case-insensitive match).
    assert StructGenHelpers.coerce("Science", FieldType.ENUM, ["science", "history"]) == "science"
    # 3. No declared whitelist -> the stripped string passes through (nothing to validate against).
    assert StructGenHelpers.coerce("  freeform  ", FieldType.ENUM, None) == "freeform"


def test_integer_drops_non_integral_numbers() -> None:
    """A fractional value for an INTEGER field is dropped, not silently truncated to its floor."""
    assert StructGenHelpers.coerce(3, FieldType.INTEGER) == 3
    assert StructGenHelpers.coerce("2024", FieldType.INTEGER) == 2024
    assert StructGenHelpers.coerce(4.0, FieldType.INTEGER) == 4  # an integral float is fine
    assert StructGenHelpers.coerce(3.7, FieldType.INTEGER) is None  # not truncated to 3
    assert StructGenHelpers.coerce("3.7", FieldType.INTEGER) is None
    assert StructGenHelpers.coerce(True, FieldType.INTEGER) is None  # a bool is never a number


def test_integer_list_drops_non_integral_items() -> None:
    """INTEGER_LIST filters fractional items instead of truncating them."""
    assert StructGenHelpers.coerce([1, 2, 3], FieldType.INTEGER_LIST) == [1, 2, 3]
    assert StructGenHelpers.coerce([1, 2.0, 3], FieldType.INTEGER_LIST) == [1, 2, 3]
    assert StructGenHelpers.coerce([1, 2.5, 3], FieldType.INTEGER_LIST) == [1, 3]  # 2.5 dropped


def test_seed_config_defaults_to_none_and_is_forwarded() -> None:
    """The optional seed is None by default and reaches the built chat client when pinned."""
    from shared_libs.pipelines.nodes.openai_compat import OpenAICompatHelpers

    # 1. It is available and defaults to unpinned.
    assert StructGenConfig().seed is None
    assert StructGenConfig(seed=42).seed == 42

    # 2. The chat helper forwards it (None when unset, the pinned value otherwise).
    endpoint = OpenAICompatConfig(base_url="http://x", model="m")
    assert OpenAICompatHelpers.chat(endpoint).seed is None
    assert OpenAICompatHelpers.chat(endpoint, seed=123).seed == 123


def test_structgen_is_registered_and_not_scored() -> None:
    assert "openai_compatible" in NodeRegistry.kinds("structgen")
    described = StructGenOpenAICompatibleNode.describe()
    assert described.scored is False
    # Every I/O slot is described (the family describe contract).
    for slot in [*described.consumes, *described.produces]:
        assert slot.description
