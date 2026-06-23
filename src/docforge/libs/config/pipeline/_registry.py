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
#
# ProviderRegistryCatalog wraps the core logic as a static-only class.
# Module-level function wrappers delegate to it so the public API (register,
# get_configs, build_union, auto_import) stays callable as before.

# ====== Standard Library Imports ======
from __future__ import annotations

import importlib
import pkgutil
from pathlib import Path
from typing import Annotated, Any, Union

# ====== Third-Party Library Imports ======
from pydantic import Field

_CATEGORIES: dict[str, dict[str, type]] = {}


class ProviderRegistryCatalog:
    """
    Static-only class encapsulating the provider auto-registration catalog.

    Manages the global ``_CATEGORIES`` dict that maps category → {provider_id → Config class}.
    Module-level wrappers (``register``, ``get_configs``, ``build_union``, ``auto_import``)
    delegate to these classmethods so callers need not change.
    """

    def __new__(cls, *args: object, **kwargs: object) -> None:
        """Block instantiation — this is a static-only catalog."""
        raise TypeError(f"{cls.__name__} is a static-only class and cannot be instantiated.")

    @staticmethod
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

    @staticmethod
    def get_configs(category: str) -> dict[str, type]:
        """
        Return all registered Config classes for a category, ordered by registration time.

        Args:
            category (str): Category key.

        Returns:
            dict[str, type]: Mapping of provider id → Config class.
        """
        return _CATEGORIES.get(category, {})

    @staticmethod
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
        return Annotated[Union[tuple(classes)], Field(discriminator="id")]  # noqa: UP007

    @staticmethod
    def auto_import(package_name: str) -> None:
        """
        Import every sub-module of a category package to trigger its @register decorators.

        Walks the category package recursively (one folder per provider, e.g.
        ``ocr/paddle/`` and ``ocr/mistral/``) and imports each module so its config class
        registers itself.  Call this at the TOP of each category __init__.py, before
        accessing get_configs().

        Args:
            package_name (str): The package name of the category (e.g. "libs.providers.ocr").
        """
        try:
            pkg = importlib.import_module(package_name)
        except ImportError:
            return
        # A namespace package (e.g. a deleted folder still resolvable) has __file__ = None;
        # there is nothing on disk to walk, so bail out instead of crashing on Path(None).
        pkg_file = getattr(pkg, "__file__", None)
        if not pkg_file:
            return
        pkg_path = Path(pkg_file).parent
        for _, modname, _ in pkgutil.walk_packages([str(pkg_path)], f"{package_name}."):
            try:
                importlib.import_module(modname)
            except ImportError:
                pass


# ──────────────────────────────────────────────────────────────────────────────
# Module-level function wrappers — keep public API unchanged.
# All callers continue to use @register("category"), get_configs(...), etc.
# ──────────────────────────────────────────────────────────────────────────────

def register(category: str):
    """
    Class decorator: register a Config class in a provider category.

    Args:
        category (str): Category key (e.g. "ocr", "vlm", "embed", "split_method").

    Returns:
        Callable: Identity decorator — returns the class unchanged after registering.
    """
    return ProviderRegistryCatalog.register(category)


def get_configs(category: str) -> dict[str, type]:
    """
    Return all registered Config classes for a category, ordered by registration time.

    Args:
        category (str): Category key.

    Returns:
        dict[str, type]: Mapping of provider id → Config class.
    """
    return ProviderRegistryCatalog.get_configs(category)


def build_union(configs: dict[str, type]) -> Any:
    """
    Build a Pydantic v2 discriminated union from a {id: ConfigClass} mapping.

    Args:
        configs (dict[str, type]): Registered config classes, keyed by provider id.

    Returns:
        Annotated union type, or Any if configs is empty.
    """
    return ProviderRegistryCatalog.build_union(configs)


def auto_import(package_name: str) -> None:
    """
    Import every module inside local/ and external/ sub-packages to trigger @register decorators.

    Args:
        package_name (str): The package name of the category (e.g. "libs.providers.ocr").
    """
    ProviderRegistryCatalog.auto_import(package_name)
