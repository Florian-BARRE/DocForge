# ====== Code Summary ======
# Builders of the public-surface snapshots: what a PyPI user can import from ``docforge_sdk`` and what
# each public resource class exposes. Everything is read through the importable public API (``__all__``,
# ``inspect``), never from the implementation files, so a module split that keeps the contract stays
# green and one that moves a class, drops a name or changes a signature fails.

# ====== Standard Library Imports ======
import enum
import importlib
import inspect
import pkgutil
from typing import Any

# ====== Third-Party Library Imports ======
from pydantic import BaseModel

# ====== Internal Project Imports ======
import docforge_sdk
from docforge_sdk import AsyncClient, Client

# Python 3.13 prints pathlib's class as ``pathlib._local.Path``; 3.12 as ``pathlib.Path``.
_SIGNATURE_ALIASES = {"pathlib._local.Path": "pathlib.Path"}

# The packages whose public (non-underscore) modules are part of the import surface.
_SURFACE_PACKAGES = ("docforge_sdk", "docforge_sdk.models", "docforge_sdk.resources")


def qualified_name(cls: type) -> str:
    """
    Name a class by where it is importable from today.

    Args:
        cls (type): The class.

    Returns:
        str: ``module.qualname``.
    """
    return f"{cls.__module__}.{cls.__qualname__}"


def signature_of(func: Any) -> str:
    """
    Render a callable's signature as one normalised string.

    Args:
        func (Any): The function or method.

    Returns:
        str: ``str(inspect.signature(func))`` with every annotation resolved to its type (so a
        ``from __future__ import annotations`` switch is no drift) and interpreter spellings normalised.
    """
    text = str(inspect.signature(func, eval_str=True))
    for raw, normalised in _SIGNATURE_ALIASES.items():
        text = text.replace(raw, normalised)
    return text


def public_methods(cls: type) -> dict[str, str]:
    """
    Snapshot a class's public methods with their signatures.

    Args:
        cls (type): The class to inspect (inherited public methods included).

    Returns:
        dict[str, str]: ``{method name: signature string}``, sorted by name.
    """
    members = inspect.getmembers(cls, predicate=inspect.isfunction)
    return {name: signature_of(func) for name, func in members if not name.startswith("_")}


def discover_public_modules() -> list[str]:
    """
    List the importable public modules of the SDK (no leading underscore), sorted.

    Returns:
        list[str]: Dotted module paths of the root package, ``models``, ``resources`` and their
        public submodules.
    """
    found = set(_SURFACE_PACKAGES)
    for package_name in _SURFACE_PACKAGES:
        package = importlib.import_module(package_name)
        for info in pkgutil.iter_modules(package.__path__):
            if not info.name.startswith("_"):
                found.add(f"{package_name}.{info.name}")
    return sorted(found)


def _describe_export(value: Any) -> dict[str, Any]:
    """
    Describe one exported object: a class (with its members) or a plain constant/alias.

    Args:
        value (Any): The object bound to an exported name.

    Returns:
        dict[str, Any]: Its kind, qualified name and, for a class, enum members or public methods.
    """
    if not inspect.isclass(value):
        # Only a plain string is a stable value; an alias's repr embeds library internals.
        described: dict[str, Any] = {"kind": "constant", "type": type(value).__name__}
        if isinstance(value, str):
            described["value"] = value
        return described
    if issubclass(value, enum.Enum):
        members = {member.name: member.value for member in value}
        return {"kind": "enum", "qualified_name": qualified_name(value), "members": members}
    if issubclass(value, BaseModel):
        # Pydantic's inherited helpers vary by version: a model's fields live in the round-trip golden.
        return {"kind": "model", "qualified_name": qualified_name(value)}
    return {
        "kind": "class",
        "qualified_name": qualified_name(value),
        "methods": public_methods(value),
    }


def module_surface(module_name: str) -> dict[str, Any]:
    """
    Snapshot one module's public exports.

    Args:
        module_name (str): The dotted module path.

    Returns:
        dict[str, Any]: ``{"__all__": sorted names or None, "exports": {name: description}}``. A
        module without ``__all__`` exports the public classes it defines.
    """
    module = importlib.import_module(module_name)
    declared = getattr(module, "__all__", None)
    if declared is None:
        names = sorted(
            name
            for name, value in vars(module).items()
            if inspect.isclass(value)
            and value.__module__ == module_name
            and not name.startswith("_")
        )
    else:
        names = sorted(declared)
    exports: dict[str, Any] = {}
    for name in names:
        value = getattr(module, name)
        # The version string moves with every release; only its presence is the contract.
        exports[name] = (
            {"kind": "version", "type": type(value).__name__}
            if name == "__version__"
            else _describe_export(value)
        )
    return {"__all__": None if declared is None else names, "exports": exports}


def clients_surface() -> dict[str, Any]:
    """
    Snapshot the two client entry points: constructor signature, public methods, wired resources.

    Returns:
        dict[str, Any]: ``{client name: {"init", "methods", "resources": {attribute: class}}}``.
    """
    surface: dict[str, Any] = {}
    for cls in (AsyncClient, Client):
        instance = cls("http://snapshot.invalid")
        resources = {
            attr: qualified_name(type(value))
            for attr, value in sorted(vars(instance).items())
            if not attr.startswith("_")
        }
        surface[cls.__name__] = {
            "init": signature_of(cls.__init__),
            "methods": public_methods(cls),
            "resources": resources,
        }
    return surface


def root_export_names() -> dict[str, list[str]]:
    """
    Snapshot the two ``__all__`` lists a ``from docforge_sdk import ...`` user relies on.

    Returns:
        dict[str, list[str]]: ``{"docforge_sdk": sorted names, "docforge_sdk.models": sorted names}``.
    """
    models = importlib.import_module("docforge_sdk.models")
    return {
        "docforge_sdk": sorted(docforge_sdk.__all__),
        "docforge_sdk.models": sorted(models.__all__),
    }
