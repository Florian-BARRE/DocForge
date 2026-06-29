# ====== Code Summary ======
# Stage auto-registration + DAG primitives — the stage-level analogue of the provider registry
# (config/pipeline/_registry.py). A stage class decorated with @register_stage self-registers in
# the global _STAGES dict (keyed by its KEY). auto_import_stages() walks the ingest stages package
# so the decorators fire (mirrors the provider auto_import). topo_order() Kahn-sorts the registered
# stages by their AFTER edges; validate_wiring() folds the produced context keys across that order
# and asserts every stage's declared CONSUMES are available and its PRODUCES are valid context keys.
#
# Adding a stage = drop a class + @register_stage; no other file changes (the PR-2 payoff).
# This module holds ONLY the registry + graph checks; instantiation/wrapping is in
# stage_assembler.py (build_pipeline).
#
# REFACTOR EXCEPTION (>200 lines): the registry catalog + the two cohesive DAG checks (topo_order,
# validate_wiring) + their flat module-level wrappers form one unit; the overage is dominated by
# the mandatory Google-style docstrings.

# ====== Standard Library Imports ======
from __future__ import annotations

import dataclasses
import importlib
import pkgutil
from pathlib import Path

# ====== Internal Project Imports ======
from common_libs.pipeline.base.stage.core import AbstractStage
from common_libs.pipeline.stages.context import PipelineContext

# Global registry: stage KEY → stage class. Populated by @register_stage at import time.
_STAGES: dict[str, type[AbstractStage]] = {}

# Packages walked by auto_import_stages so every stage's @register_stage fires. All ingest stages
# are now native under ``ingest.stages`` (the adapters package was removed once every stage migrated).
_STAGE_PACKAGES = ("common_libs.pipeline.ingest.stages",)

# Context keys available BEFORE any stage runs (externally-provided run inputs). Used as the
# wiring-validation roots: a stage may consume these without any prior stage producing them.
ROOT_CONTEXT_KEYS: frozenset[str] = frozenset(
    {"original_bytes", "filename", "doc_id", "collection_id", "metadata_fields", "doc_user_meta"}
)


class StageWiringError(RuntimeError):
    """Raised when the registered stage graph is invalid (cycle, unknown dep, or broken IO wiring)."""


class StageRegistryCatalog:
    """
    Static-only catalog encapsulating the stage registry + DAG primitives.

    Module-level wrappers (``register_stage``/``get_stages``/``auto_import_stages``/``topo_order``/
    ``validate_wiring``) delegate here so callers need not touch the class directly.
    """

    def __new__(cls, *args: object, **kwargs: object) -> None:  # type: ignore[misc]
        """Block instantiation — this is a static-only catalog."""
        raise TypeError(f"{cls.__name__} is a static-only class and cannot be instantiated.")

    @staticmethod
    def register_stage(cls: type[AbstractStage]) -> type[AbstractStage]:
        """
        Class decorator: register a stage class in the global catalog, keyed by ``cls.SPEC.key``.

        Args:
            cls (type[AbstractStage]): The concrete stage class to register.

        Returns:
            type[AbstractStage]: The class unchanged (decorator identity).
        """
        _STAGES[cls.SPEC.key] = cls
        return cls

    @staticmethod
    def get_stages() -> dict[str, type[AbstractStage]]:
        """Return the registered stages, keyed by KEY (registration order preserved)."""
        return dict(_STAGES)

    @staticmethod
    def auto_import_stages() -> None:
        """
        Import every module in the stage packages so their @register_stage decorators fire.

        Walks each package in ``_STAGE_PACKAGES`` (the native ingest stages). Mirrors the
        provider-registry ``auto_import``: idempotent, swallows per-module ImportError so a
        partially-available environment never breaks discovery of the rest.
        """
        for package in _STAGE_PACKAGES:
            try:
                pkg = importlib.import_module(package)
            except ImportError:
                continue
            pkg_file = getattr(pkg, "__file__", None)
            if not pkg_file:
                continue
            pkg_path = Path(pkg_file).parent
            for _, modname, _ in pkgutil.walk_packages([str(pkg_path)], f"{package}."):
                try:
                    importlib.import_module(modname)
                except ImportError:
                    pass

    @staticmethod
    def topo_order(stages: list[type[AbstractStage]]) -> list[type[AbstractStage]]:
        """
        Topologically order stage classes by their ``AFTER`` edges (Kahn, declaration-stable).

        Args:
            stages (list[type[AbstractStage]]): The stage classes to order.

        Returns:
            list[type[AbstractStage]]: The classes in a valid execution order.

        Raises:
            StageWiringError: On an ``AFTER`` reference to an unknown stage, or a dependency cycle.
        """
        # 1. Validate every AFTER edge resolves to a known stage.
        by_key = {s.SPEC.key: s for s in stages}
        for stage in stages:
            for dep in stage.SPEC.after:
                if dep not in by_key:
                    raise StageWiringError(
                        f"Stage {stage.SPEC.key!r} declares AFTER={dep!r} but no such stage is registered."
                    )

        # 2. Kahn's algorithm, preserving declaration order among ready stages.
        remaining = list(stages)
        resolved: set[str] = set()
        ordered: list[type[AbstractStage]] = []
        while remaining:
            ready = [s for s in remaining if all(dep in resolved for dep in s.SPEC.after)]
            if not ready:
                cyclic = ", ".join(s.SPEC.key for s in remaining)
                raise StageWiringError(f"Cycle in stage dependency graph among: {cyclic}.")
            for stage in ready:
                ordered.append(stage)
                resolved.add(stage.SPEC.key)
                remaining.remove(stage)
        return ordered

    @staticmethod
    def validate_wiring(ordered: list[type[AbstractStage]]) -> None:
        """
        Validate the IO graph: every CONSUMES is produced upstream; every PRODUCES is a known key.

        Folds a ``produced`` set across the topo order starting from the externally-provided root
        keys; each stage must consume only already-produced keys, and may only declare context keys
        (PipelineContext fields) as IO.

        Args:
            ordered (list[type[AbstractStage]]): Stage classes in topological order.

        Raises:
            StageWiringError: When a stage consumes an unproduced key, or declares an IO key that is
                not a PipelineContext field.
        """
        valid_keys = {f.name for f in dataclasses.fields(PipelineContext)}
        # The root inputs themselves must be real context fields — a guard against ROOT_CONTEXT_KEYS
        # drifting out of sync with PipelineContext (which would silently admit a broken graph).
        unknown_roots = ROOT_CONTEXT_KEYS - valid_keys
        if unknown_roots:
            raise StageWiringError(
                f"ROOT_CONTEXT_KEYS contains {sorted(unknown_roots)} which are not PipelineContext fields."
            )
        produced: set[str] = set(ROOT_CONTEXT_KEYS)
        for stage in ordered:
            # 1. Declared IO keys must be real context fields.
            for key in (*stage.SPEC.consumes, *stage.SPEC.produces):
                if key not in valid_keys:
                    raise StageWiringError(
                        f"Stage {stage.SPEC.key!r} declares IO key {key!r} that is not a PipelineContext field."
                    )
            # 2. Everything consumed must already be produced (or be a root input).
            missing = set(stage.SPEC.consumes) - produced
            if missing:
                raise StageWiringError(
                    f"Stage {stage.SPEC.key!r} consumes {sorted(missing)} which no upstream stage produces."
                )
            produced |= set(stage.SPEC.produces)


# ──────────────────────────────────────────────────────────────────────────────
# Module-level function wrappers — keep the public API flat (mirrors _registry.py).
# ──────────────────────────────────────────────────────────────────────────────


def register_stage(cls: type[AbstractStage]) -> type[AbstractStage]:
    """Class decorator: register a stage class in the global catalog (keyed by ``cls.SPEC.key``)."""
    return StageRegistryCatalog.register_stage(cls)


def get_stages() -> dict[str, type[AbstractStage]]:
    """Return the registered stages, keyed by KEY."""
    return StageRegistryCatalog.get_stages()


def auto_import_stages() -> None:
    """Import the adapters package so every @register_stage decorator fires."""
    StageRegistryCatalog.auto_import_stages()


def topo_order(stages: list[type[AbstractStage]]) -> list[type[AbstractStage]]:
    """Topologically order stage classes by their AFTER edges (raises StageWiringError)."""
    return StageRegistryCatalog.topo_order(stages)


def validate_wiring(ordered: list[type[AbstractStage]]) -> None:
    """Validate the CONSUMES/PRODUCES graph across the topo order (raises StageWiringError)."""
    StageRegistryCatalog.validate_wiring(ordered)


__all__ = [
    "StageWiringError",
    "ROOT_CONTEXT_KEYS",
    "register_stage",
    "get_stages",
    "auto_import_stages",
    "topo_order",
    "validate_wiring",
]
