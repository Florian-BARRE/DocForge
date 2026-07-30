# ====== Code Summary ======
# Write-time validation of a stored SEARCH graph blob. It layers a terminal-CONTRACT check on top of
# the shared structural PipelineBlobValidator: a search blob must not only build + pass the graph
# validator, it must ALSO be a genuine search pipeline — one that ends on a node producing a
# SearchResult (the deliver/hits contract the inline runner asserts at run time). This closes the gap
# where a structurally-valid-but-non-search graph (an ingest topology, or a search graph missing its
# deliver terminal) stored a 200, then made every subsequent query raise SearchRunError → HTTP 500.
# The terminal check mirrors the runner's runtime assert at BUILD time, so the blob fails fast at the
# write boundary (422) instead of spending a broken graph on every read.

# ====== Third-Party Library Imports ======
from fastapi import HTTPException
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

# ====== Local Project Imports ======
from ..context import CONTEXT
from .pipeline_validation import PipelineBlobValidator


class SearchBlobValidator:
    """
    Static validator for a stored search graph blob (structural + terminal contract → 422).

    Composes the shared structural ``PipelineBlobValidator`` (build + graph validation) with a
    terminal-output check that mirrors the inline runner's runtime assert: the built graph must
    terminate on a node whose ``Produces`` face yields a ``SearchResult``. A structurally valid but
    non-search graph (an ingest topology, or a search graph with its ``deliver/hits`` terminal
    removed) is therefore rejected at the WRITE boundary — never stored to 500 on every query.
    """

    logger = loggerplusplus.bind(identifier="SearchBlobValidator")

    def __new__(cls, *args: object, **kwargs: object) -> None:
        raise TypeError("SearchBlobValidator is a static-only class and cannot be instantiated.")

    @classmethod
    def __produces_search_result(cls, node: AbstractNode) -> bool:
        """
        Return whether a node's terminal output is a ``SearchResult``.

        Mirrors the runner's ``isinstance(output.result, SearchResult)`` assert, but reads the
        node's static ``Produces`` face at build time (no execution). A group's output is its OWN
        terminal's, so groups recurse; a ``ForEach`` emits a ``list`` and can never be the single
        SearchResult terminal.

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
            return cls.__has_search_result_exit(node)
        # 3. A ForEach produces a list[...] — never a single SearchResult terminal.
        return False

    @classmethod
    def __has_search_result_exit(cls, group: Group) -> bool:
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

    @classmethod
    def validate(cls, blob: dict) -> None:
        """
        Structurally validate a search blob AND assert it is a genuine search pipeline.

        Args:
            blob (dict): The stored search graph configuration to check.

        Raises:
            HTTPException: 422 when the blob cannot be built or fails structural validation
                (delegated to ``PipelineBlobValidator``), or when the built graph does not
                terminate on a ``deliver/hits`` node producing a SearchResult.
        """
        # 1. Structural validation first — build + graph validator (shared chokepoint, raises 422).
        PipelineBlobValidator.validate(blob)

        # 2. Re-build the now-known-valid graph and assert its TERMINAL contract (the runner's
        #    runtime assert, checked at build time so a non-search graph fails at the write edge).
        group = CONTEXT.pipeline_builder.build(blob)
        if not cls.__has_search_result_exit(group):
            raise HTTPException(
                status_code=422,
                detail=(
                    "Stored search blob is not a valid search pipeline — it must end on a "
                    "deliver/hits node producing a SearchResult."
                ),
            )


__all__ = ["SearchBlobValidator"]
