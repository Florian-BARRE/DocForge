# ====== Code Summary ======
# Characterization of the SDK models (safety net of the R-24 models split, and a detector of hidden
# type drift). For every published model a payload is synthesised from its own JSON schema (all
# properties, then required ones only), parsed into the model and dumped back to JSON: the dumps, the
# field annotations and the required-ness are the golden. A dumped payload must also survive a second
# parse unchanged. A diff is a public-contract decision, never a test to fix.

# ====== Standard Library Imports ======
import inspect
import json
import re
from typing import Any

# ====== Third-Party Library Imports ======
import pytest
from pydantic import BaseModel, ValidationError

# ====== Local Project Imports ======
from tests.characterization.support.golden import assert_matches_golden
from tests.characterization.support.models_under_test import models_under_test
from tests.characterization.support.payloads import PayloadSynthesizer

_MODELS = models_under_test()
_MODULE_PREFIX = re.compile(r"docforge_sdk\.models\.[a-z_]+\.")


def _dump(model: type[BaseModel], full: bool) -> Any:
    """
    Parse a synthesised payload and dump it back, or name the validation errors that refused it.

    Args:
        model (type[BaseModel]): The model.
        full (bool): Synthesise every property (True) or only the required ones.

    Returns:
        Any: The JSON dump, or ``{"rejected": [error type/location, ...]}`` for a model whose own
        validators refuse a schema-valid payload (a cross-field rule the schema cannot express).
    """
    payload = PayloadSynthesizer(model.model_json_schema(), full=full).build()
    try:
        return model.model_validate(payload).model_dump(mode="json")
    except ValidationError as error:
        return {
            "rejected": [f"{'.'.join(map(str, e['loc']))}: {e['type']}" for e in error.errors()]
        }


def _annotation(annotation: Any) -> str:
    """Render a field type with model classes by bare name, so moving a model between modules is no drift."""
    return _MODULE_PREFIX.sub("", inspect.formatannotation(annotation))


def _snapshot(model: type[BaseModel]) -> dict[str, Any]:
    """Build the golden entry of one model."""
    return {
        "fields": {
            name: {"annotation": _annotation(info.annotation), "required": info.is_required()}
            for name, info in model.model_fields.items()
        },
        "full": _dump(model, full=True),
        "minimal": _dump(model, full=False),
    }


def test_every_model_round_trips_to_the_golden_shape() -> None:
    assert_matches_golden(
        "model_round_trip.json", {name: _snapshot(m) for name, m in _MODELS.items()}
    )


def _accepted_payloads() -> list[tuple[str, bool]]:
    """Every (model, full?) pair whose synthesised payload the model accepts (rejections are golden)."""
    return [
        (name, full)
        for name, model in _MODELS.items()
        for full in (True, False)
        if "rejected" not in _dump(model, full=full)
    ]


@pytest.mark.parametrize(("name", "full"), _accepted_payloads())
def test_a_dumped_model_parses_back_to_the_same_dump(name: str, full: bool) -> None:
    model = _MODELS[name]
    dumped = _dump(model, full=full)
    assert model.model_validate(dumped).model_dump(mode="json") == json.loads(json.dumps(dumped))
