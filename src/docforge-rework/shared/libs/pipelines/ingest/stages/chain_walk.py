# ====== Code Summary ======
# ChainWalker — the generic "read a provider chain back out of a graph" helper shared by every reader
# that derives a ChainSpec from transitions (the parse/embed linear stages, each enrich per-figure
# branch, and each metagen structgen ladder). Given the family node set and the escalation edges, it
# finds the chain HEAD (the only family node no in-family edge targets) and WALKS the chain forward,
# reading each step's kind/config and the ScoreBelow threshold that escalates it to the next step. It
# is pure topology reading — it never touches the stage state — so the same four rules serve every
# call-site without each reader re-implementing the walk.

# ====== Third-Party Library Imports ======
from loggerplusplus import loggerplusplus

# ====== Internal Project Imports ======
from shared_libs.pipelines.base import ScoreBelow
from shared_libs.pipelines.build.blob import ActionNodeBlob

# ====== Local Project Imports ======
from .models import ChainStep


class ChainWalker:
    """Static reader of a provider chain from a graph's transitions and family node set."""

    logger = loggerplusplus.bind(identifier="ChainWalker")

    def __new__(cls, *args: object, **kwargs: object) -> None:
        raise TypeError("ChainWalker is a static-only class and cannot be instantiated.")

    @classmethod
    def head(
        cls, transitions: list, by_id: dict[str, ActionNodeBlob], families: set[str]
    ) -> ActionNodeBlob:
        """The chain's head — the only family node no in-family escalation edge points at."""
        targeted = {
            transition.to_node_id
            for transition in transitions
            if transition.from_node_id in by_id
            and transition.to_node_id in by_id
            and by_id[transition.to_node_id].family in families
        }
        return next(
            (node for node_id, node in by_id.items() if node_id not in targeted),
            next(iter(by_id.values())),
        )

    @classmethod
    def walk(
        cls,
        transitions: list,
        by_id: dict[str, ActionNodeBlob],
        head: ActionNodeBlob,
        families: set[str],
    ) -> list[ChainStep]:
        """Follow a chain's providers from its head, reading the score_below escalation off the edges."""
        steps: list[ChainStep] = []
        current: ActionNodeBlob | None = head
        seen: set[str] = set()
        while current is not None and current.family in families and current.id not in seen:
            seen.add(current.id)
            steps.append(
                ChainStep(
                    kind=current.kind,
                    config=dict(current.config),
                    score_below=cls.__score_below(transitions, current.id, by_id, families),
                )
            )
            current = cls.__next_step(transitions, current.id, by_id, families)
        return steps

    @classmethod
    def __score_below(
        cls, transitions: list, node_id: str, by_id: dict[str, ActionNodeBlob], families: set[str]
    ) -> float | None:
        """The threshold of the ScoreBelow edge escalating this step to the next chain node."""
        for transition in transitions:
            if (
                transition.from_node_id == node_id
                and isinstance(transition.condition, ScoreBelow)
                and transition.to_node_id in by_id
                and by_id[transition.to_node_id].family in families
            ):
                return transition.condition.threshold
        return None

    @classmethod
    def __next_step(
        cls, transitions: list, node_id: str, by_id: dict[str, ActionNodeBlob], families: set[str]
    ) -> ActionNodeBlob | None:
        """The next chain provider a step escalates to (score_below / on_failure target)."""
        for transition in transitions:
            target = by_id.get(transition.to_node_id)
            if (
                transition.from_node_id == node_id
                and target is not None
                and target.family in families
            ):
                return target
        return None


__all__ = ["ChainWalker"]
