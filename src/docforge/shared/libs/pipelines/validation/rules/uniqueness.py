# ====== Code Summary ======
# The whole-graph uniqueness rule: a node kind declared UNIQUE_IN_GRAPH may appear at most once in
# the ENTIRE graph (nested groups and foreach bodies included). Unlike the per-group rules, this one
# walks the full tree from the root and reports one issue per duplicated kind, naming every instance
# so the UI can badge them all.

# ====== Third-Party Library Imports ======
from loggerplusplus import loggerplusplus

# ====== Internal Project Imports ======
from shared_libs.pipelines.base import ActionNode, ForEach, Group

# ====== Local Project Imports ======
from ..issues import ValidationCode
from .collector import IssueCollector


class UniquenessRules:
    """Static-only rule rejecting any UNIQUE_IN_GRAPH kind that appears more than once."""

    logger = loggerplusplus.bind(identifier="UniquenessRules")

    def __new__(cls, *args: object, **kwargs: object) -> None:
        raise TypeError("UniquenessRules is a static-only class and cannot be instantiated.")

    @classmethod
    def check(cls, root: Group, collector: IssueCollector) -> None:
        """Reject any UNIQUE_IN_GRAPH kind appearing more than once in the WHOLE graph."""
        # 1. Walk the full tree (nested groups and foreach bodies included), counting per kind.
        occurrences: dict[str, list[str]] = {}

        def walk(group: Group) -> None:
            for child in group.children:
                if isinstance(child, ActionNode) and child.UNIQUE_IN_GRAPH:
                    occurrences.setdefault(child.KIND, []).append(child.id)
                elif isinstance(child, Group):
                    walk(child)
                elif isinstance(child, ForEach):
                    walk(child.body)

        walk(root)

        # 2. One issue per duplicated kind, naming every instance so the UI can badge them all.
        for kind, ids in occurrences.items():
            if len(ids) > 1:
                collector.record(
                    ValidationCode.DUPLICATE_UNIQUE_NODE,
                    f"group '{root.id}'",
                    f"node kind '{kind}' is single-use but appears {len(ids)} times "
                    f"({', '.join(ids)})",
                )


__all__ = ["UniquenessRules"]
