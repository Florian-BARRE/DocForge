# ====== Code Summary ======
# ReplayStageMap — classifies every ROOT node of a built ingestion graph into its canonical stage
# (StageKey), from the node's registry family (and, for metagen, its scope kind). A ForEach root takes
# the stage of the node producing the list it iterates. This is the read the replay planner uses to
# find where a stage starts and which upstream producers a mid-graph run must stand on; it is pure
# topology (no I/O) and tolerates edited blobs — an unclassifiable root simply maps to None.

# ====== Internal Project Imports ======
from shared_libs.pipelines.base import ActionNode, ForEach, FromNode, Group
from shared_libs.pipelines.ingest.stages import StageKey, StageSpecs
from shared_libs.pipelines.registry import NodeRegistry

# Registry family → its stage (metagen is split by scope below, ForEach by its list's producer).
_FAMILY_STAGE: dict[str, StageKey] = {
    "intake": StageKey.INTAKE,
    "converter": StageKey.CONVERT,
    "parser": StageKey.PARSE,
    "docmeta": StageKey.LANGUAGE,
    "render": StageKey.RENDER,
    "enrich": StageKey.ENRICH,
    "chunker": StageKey.CHUNK,
    "contextualize": StageKey.CONTEXTUALIZE,
    "embed": StageKey.EMBED,
    "deliver": StageKey.DELIVER,
}

# The canonical run order of the stages (the skeleton rail), as a rank for comparisons.
STAGE_RANK: dict[StageKey, int] = {meta.key: index for index, meta in enumerate(StageSpecs.ORDER)}


class ReplayStageMap:
    """Static-only helper: map a built graph's root nodes to their canonical stages."""

    def __new__(cls, *args: object, **kwargs: object) -> None:
        raise TypeError("ReplayStageMap is a static-only class and cannot be instantiated.")

    @staticmethod
    def __action_stage(node: ActionNode) -> StageKey | None:
        """The stage of one action root, from its registry family (metagen split by scope)."""
        family = NodeRegistry.family_of(type(node))
        if family == "metagen":
            return StageKey.METAGEN_DOCUMENT if "document" in node.KIND else StageKey.METAGEN_CHUNK
        return _FAMILY_STAGE.get(family or "")

    @classmethod
    def classify(cls, group: Group) -> dict[str, StageKey | None]:
        """
        Classify every root child of a built ingestion graph.

        Args:
            group (Group): The built root group.

        Returns:
            dict[str, StageKey | None]: Root node id → its stage (None when unclassifiable).
        """
        # 1. Action roots first — their family decides directly.
        stages: dict[str, StageKey | None] = {}
        for child in group.children:
            stages[child.id] = cls.__action_stage(child) if isinstance(child, ActionNode) else None

        # 2. A ForEach root belongs to the stage of the node producing the list it iterates.
        for child in group.children:
            if isinstance(child, ForEach) and isinstance(child.over, FromNode):
                stages[child.id] = stages.get(child.over.node_id)
        return stages


__all__ = ["ReplayStageMap", "STAGE_RANK"]
