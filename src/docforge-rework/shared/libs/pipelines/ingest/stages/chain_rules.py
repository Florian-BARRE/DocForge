# ====== Code Summary ======
# ChainRules — the build-safe config defaulting and family-level chain rules the compiler applies
# when it (re)builds a chain or picks a provider. Kept apart from the compiler so the "how a step's
# config is completed / which escalations a family allows / which kinds are single-use" logic lives
# in one cohesive, testable place, and the compiler stays a thin dispatcher over PipelineState. Every
# method returns DATA (completed steps, a scored flag, notice strings) — it never mutates state and
# never raises for a user-reachable condition, so the compiler can surface issues as notices.

# ====== Standard Library Imports ======
from typing import Any

# ====== Third-Party Library Imports ======
from loggerplusplus import loggerplusplus

# ====== Internal Project Imports ======
from shared_libs.pipelines.base import ScoredOutput
from shared_libs.pipelines.registry import NodeRegistry

# ====== Local Project Imports ======
from .models import ChainStep


class ChainRules:
    """Static build-safe config defaulting + family-level chain rules shared by the compiler."""

    logger = loggerplusplus.bind(identifier="ChainRules")

    def __new__(cls, *args: object, **kwargs: object) -> None:
        raise TypeError("ChainRules is a static-only class and cannot be instantiated.")

    @classmethod
    def unknown_kind_notices(cls, family: str, steps: list[ChainStep]) -> list[str]:
        """Notices for chain steps whose kind is not a registered provider of ``family``.

        A non-empty result means the caller must leave the blob unchanged: completing an unknown
        kind's config would call ``NodeRegistry.get`` and RAISE, breaking the compiler's
        "nonsensical action is DATA, never an exception" contract.

        Args:
            family (str): The registry family every step must draw its kind from.
            steps (list[ChainStep]): The proposed chain steps.

        Returns:
            list[str]: One notice per unknown kind (empty when every kind is valid).
        """
        available = set(NodeRegistry.kinds(family))
        return [
            f"'{step.kind}' is not a '{family}' provider"
            for step in steps
            if step.kind not in available
        ]

    @classmethod
    def reset_config(cls, family: str, kind: str) -> dict[str, Any]:
        """Schema-default config for a kind — required (default-less) fields filled build-safe."""
        node_class = NodeRegistry.get(family, kind)
        config: dict[str, Any] = {}
        for name, field in node_class.Config.model_fields.items():
            if field.is_required():
                config[name] = cls.__empty_value(field.annotation)
        return config

    @classmethod
    def complete_steps(cls, family: str, steps: list[ChainStep]) -> list[ChainStep]:
        """Complete every step's config with build-safe schema defaults (same rule as a provider swap).

        A required api_key/base_url becomes "" — the blob always BUILDS, and the gap surfaces as a
        fillable field, never a 500.
        """
        return [
            step.model_copy(update={"config": {**cls.reset_config(family, step.kind), **step.config}})
            for step in steps
        ]

    @classmethod
    def drop_unscored_thresholds(
        cls, family: str, steps: list[ChainStep]
    ) -> tuple[list[ChainStep], str | None]:
        """Strip score_below from a non-scored family's chain — its fallback is failure-only.

        Returns:
            tuple[list[ChainStep], str | None]: The (possibly stripped) steps and a notice when a
            threshold was dropped, else ``None``.
        """
        if cls.family_scored(family) or not any(step.score_below is not None for step in steps):
            return steps, None
        stripped = [step.model_copy(update={"score_below": None}) for step in steps]
        return stripped, f"'{family}' fallback is failure-only — dropped the score thresholds"

    @classmethod
    def duplicate_unique_notices(cls, family: str, steps: list[ChainStep]) -> list[str]:
        """Notices for single-use (UNIQUE_IN_GRAPH) kinds repeated in a chain — the build rejects it."""
        notices: list[str] = []
        seen: set[str] = set()
        for step in steps:
            if step.kind in seen and NodeRegistry.get(family, step.kind).UNIQUE_IN_GRAPH:
                notices.append(f"'{step.kind}' can appear only once — repeating it will fail the build")
            seen.add(step.kind)
        return notices

    @classmethod
    def family_scored(cls, family: str) -> bool:
        """Whether a family's producers are score-bearing (gates ScoreBelow escalation)."""
        kinds = NodeRegistry.kinds(family)
        return bool(kinds) and issubclass(NodeRegistry.get(family, kinds[0]).Produces, ScoredOutput)

    @staticmethod
    def __empty_value(annotation: object) -> Any:
        """
        A build-safe zero value for a required field of the given annotation.

        LIMITATION: this fills a required int/float with 0/0.0 and does NOT honour a declared
        lower bound — a required numeric field with ``Field(gt=0)`` would fail ``model_validate``
        at assembly (a ``build_error``, surfaced as fixable data, never a crash). Unsupported by
        design today: every provider's required fields are strings (base_url/api_key/model). Add
        bound-awareness here only when a required-and-bounded numeric config field first appears.
        """
        return {str: "", int: 0, float: 0.0, bool: False, list: [], dict: {}}.get(annotation, "")


__all__ = ["ChainRules"]
