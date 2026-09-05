# ====== Code Summary ======
# The search-pipeline TERMINAL contract, expressed on a BUILT graph and shared by every write
# boundary. A genuine search graph must terminate on a node whose static Produces face yields a
# SearchResult (the deliver/hits contract the inline SearchRunner asserts at run time). Kept in
# shared_libs so BOTH the app's write-time SearchBlobValidator (→ HTTP 422) and the worker's
# import-time validator (the collection transfer restore) apply the exact same rule without the
# worker importing anything app-side — the check reads only static Produces faces, never executes.

# ====== Third-Party Library Imports ======
from loggerplusplus import loggerplusplus

# ====== Internal Project Imports ======
from shared_libs.pipelines.base import (
    AbstractNode,
    ActionNode,
    GraphTopology,
    Group,
    SlotTypes,
)
from shared_libs.public_models.search import SearchResult


class SearchResultContract:
    """
    Static check that a built graph terminates on a SearchResult-producing node.

    Mirrors the inline runner's ``isinstance(output.result, SearchResult)`` assert, but reads each
    node's static ``Produces`` face at build time (no execution). The single source of truth for
    "is this a genuine search pipeline?", shared by the app write boundary and the import restore.
    """

    logger = loggerplusplus.bind(identifier="SearchResultContract")

    def __new__(cls, *args: object, **kwargs: object) -> None:
        raise TypeError("SearchResultContract is a static-only class and cannot be instantiated.")

    @classmethod
    def __produces_search_result(cls, node: AbstractNode) -> bool:
        """
        Return whether a node's terminal output is a ``SearchResult``.

        A group's output is its OWN terminal's, so groups recurse; a ``ForEach`` emits a ``list``
        and can never be the single SearchResult terminal.

        Args:
            node (AbstractNode): A built graph node (leaf, group, or ForEach).

        Returns:
            bool: True when this node delivers a SearchResult.
        """
        # 1. A leaf: inspect its PRODUCES slots for a SearchResult-typed artefact.
        if isinstance(node, ActionNode):
            for field_info in node.Produces.model_fields.values():
                element, _is_list = SlotTypes.element(field_info.annotation)
                if isinstance(element, type) and issubclass(element, SearchResult):
                    return True
            return False
        # 2. A nested group: its output is its own terminal's — recurse into its exits.
        if isinstance(node, Group):
            return cls.terminates_on_search_result(node)
        # 3. A ForEach produces a list[...] — never a single SearchResult terminal.
        return False

    @classmethod
    def terminates_on_search_result(cls, group: Group) -> bool:
        """
        Return whether the group terminates on a SearchResult-producing node.

        Args:
            group (Group): The built search graph (or a nested sub-group).

        Returns:
            bool: True when at least one exit node (no outgoing transition) delivers a SearchResult.
        """
        # 1. The exit nodes: children that are never a transition source (the graph's terminals).
        child_ids = {child.id for child in group.children}
        exit_ids = set(GraphTopology.exits(child_ids, group.transitions))
        # 2. At least one exit must deliver a SearchResult to match the runner's output contract.
        return any(
            cls.__produces_search_result(child) for child in group.children if child.id in exit_ids
        )


__all__ = ["SearchResultContract"]
