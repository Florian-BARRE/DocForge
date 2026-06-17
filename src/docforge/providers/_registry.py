# ====== Code Summary ======
# Provider auto-registration system.
#
# Any Config class decorated with @register("category") self-registers in the global
# _CATEGORIES dict. Category __init__.py calls auto_import(__package__) to discover
# all submodules (triggering decorators), then build_union(get_configs("category"))
# to create a typed Pydantic discriminated union.
#
# Adding a new provider = create a file, inherit from base, annotate @register.
# No other file needs changing.

# ====== Standard Library Imports ======
from __future__ import annotations

import importlib
import pkgutil
from pathlib import Path
from typing import Annotated, Any, Union

# ====== Third-Party Library Imports ======
from pydantic import Field

_CATEGORIES: dict[str, dict[str, type]] = {}


def register(category: str):
    """
    Class decorator: register a Config class in a provider category.

    Args:
        category (str): Category key (e.g. "ocr", "vlm", "embed", "split_method").

    Returns:
        Callable: Identity decorator — returns the class unchanged after registering.
    """
    def decorator(cls: type) -> type:
        provider_id = cls.model_fields["id"].default
        _CATEGORIES.setdefault(category, {})[provider_id] = cls
        return cls
    return decorator


def get_configs(category: str) -> dict[str, type]:
    """
    Return all registered Config classes for a category, ordered by registration time.

    Args:
        category (str): Category key.

    Returns:
        dict[str, type]: Mapping of provider id → Config class.
    """
    return _CATEGORIES.get(category, {})


def build_union(configs: dict[str, type]) -> Any:
    """
    Build a Pydantic v2 discriminated union from a {id: ConfigClass} mapping.

    The resulting type is Annotated[Union[A, B, ...], Field(discriminator="id")],
    compatible with Pydantic model fields for validated polymorphic deserialization.

    Args:
        configs (dict[str, type]): Registered config classes, keyed by provider id.

    Returns:
        Annotated union type, or Any if configs is empty.
    """
    if not configs:
        return Any
    classes = list(configs.values())
    if len(classes) == 1:
        return Annotated[classes[0], Field(discriminator="id")]
    return Annotated[Union[tuple(classes)], Field(discriminator="id")]


def auto_import(package_name: str) -> None:
    """
    Import every module inside local/ and external/ sub-packages to trigger @register decorators.

    Call this at the TOP of each category __init__.py, before accessing get_configs().

    Args:
        package_name (str): The package name of the category (e.g. "libs.providers.ocr").
    """
    for sub in ("local", "external"):
        subpkg = f"{package_name}.{sub}"
        try:
            pkg = importlib.import_module(subpkg)
            pkg_path = Path(pkg.__file__).parent  # type: ignore[arg-type]
            for _, modname, _ in pkgutil.walk_packages([str(pkg_path)], f"{subpkg}."):
                try:
                    importlib.import_module(modname)
                except ImportError:
                    pass
        except ImportError:
            pass
