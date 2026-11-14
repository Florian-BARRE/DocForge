# ====== Code Summary ======
# Which response/request models the round-trip characterization covers: every pydantic model the SDK
# publishes in ``docforge_sdk.models.__all__`` plus every model a public resource method returns (some,
# like ``DocumentView``, are returned but not re-exported). Discovered through the public API only.

# ====== Standard Library Imports ======
import importlib
import inspect
import typing
from typing import Any

# ====== Third-Party Library Imports ======
from pydantic import BaseModel

# ====== Local Project Imports ======
from .surface import clients_surface


def _models_in(annotation: Any) -> list[type[BaseModel]]:
    """Unwrap ``list[...]`` / unions / ``Annotated`` down to the pydantic model classes inside."""
    if inspect.isclass(annotation) and issubclass(annotation, BaseModel):
        return [annotation]
    found: list[type[BaseModel]] = []
    for arg in typing.get_args(annotation):
        found.extend(_models_in(arg))
    return found


def _register(found: dict[str, type[BaseModel]], model: type[BaseModel]) -> None:
    """Add a model under its class name, refusing two different classes with one name."""
    existing = found.setdefault(model.__name__, model)
    if existing is not model:
        raise AssertionError(f"two public SDK models are both named {model.__name__}")


def models_under_test() -> dict[str, type[BaseModel]]:
    """
    Collect the models, keyed by class name (``JobStatus``): a module move is the surface golden's concern, not this one's.

    Returns:
        dict[str, type[BaseModel]]: Sorted by class name (unique across the SDK, asserted).
    """
    found: dict[str, type[BaseModel]] = {}

    # 1. Everything the models package publishes.
    package = importlib.import_module("docforge_sdk.models")
    for name in package.__all__:
        for m in _models_in(getattr(package, name)):
            _register(found, m)

    # 2. Everything a public resource method returns (the response models of the wire).
    for qualified in clients_surface()["AsyncClient"]["resources"].values():
        module_name, class_name = qualified.rsplit(".", 1)
        resource = getattr(importlib.import_module(module_name), class_name)
        for _, func in inspect.getmembers(resource, predicate=inspect.isfunction):
            if func.__name__.startswith("_"):
                continue
            returned = inspect.signature(func, eval_str=True).return_annotation
            for m in _models_in(returned):
                _register(found, m)
    return dict(sorted(found.items()))
