# ====== Code Summary ======
# SearchPipeline — the class that TIES the search pipeline together: it declares which node families
# compose it, triggers their registration, is the origin of the palette the UI is populated from,
# and carries the default topology (the minimal P1 graph: normalize → encode → retrieve(hybrid) →
# hydrate → deliver(hits)). It is the search analog of IngestPipeline: same engine, same builder,
# same validator — only the families, run inputs and default blob differ.

# ====== Internal Project Imports ======
import shared_libs.pipelines.search.nodes  # noqa: F401 — registers the search node families
from shared_libs.pipelines.base import FromNode, FromRunInput, IoSlot, Transition
from shared_libs.pipelines.build import ActionNodeBlob, GroupNodeBlob
from shared_libs.pipelines.introspection import (
    ArtefactCatalog,
    FamilyCatalog,
    GraphMechanics,
    Palette,
)
from shared_libs.pipelines.registry import NodeRegistry


class SearchPipeline:
    """Static entry point of the search pipeline — its families, its palette, its topology."""

    # The families a search pipeline is assembled from, in stage order; deliver is the reused
    # capability family shared with ingestion (its ``hits`` kind).
    FAMILIES = (
        "query", "encode", "retrieve", "fuse", "rerank", "postprocess", "deliver",
    )

    # Per-family kind allowlist for SHARED families: ``deliver`` is reused by ingestion, so its
    # palette view must be scoped to search's own terminal kind (``hits``) — otherwise ingestion's
    # ``bundle`` would leak into the search palette. Exclusive families stay unrestricted.
    FAMILY_KINDS: dict[str, set[str]] = {"deliver": {"hits"}}

    # The artefacts the RUN hands to the graph — the sources a FromRunInput binding can target.
    RUN_INPUTS = (
        IoSlot(
            name="query",
            artefact_type="RawQuery",
            description="The caller's raw query: text, requested top_k and retrieval flags.",
        ),
        IoSlot(
            name="filters",
            artefact_type="QueryFilters",
            description="The caller's raw field → value filter map applied to the retrieval.",
        ),
        IoSlot(
            name="contract",
            artefact_type="SearchContract",
            description=(
                "The collection's search contract: its identity, its own embedder (kind + config) "
                "and its filterable field names."
            ),
        ),
    )

    def __new__(cls, *args: object, **kwargs: object) -> None:
        raise TypeError("SearchPipeline is a static-only class and cannot be instantiated.")

    @classmethod
    def palette(cls, full: bool = False) -> Palette:
        """
        The UI palette of the search pipeline — every block available to assemble it.

        Mirrors IngestPipeline.palette: the default palette carries only the families (each node
        with its full describe() card); the FULL palette adds the graph-level vocabulary (run
        inputs, mechanics, artefacts) for the advanced, headless design surface.

        Args:
            full (bool): When True, also fill run_inputs, mechanics and artefacts.

        Returns:
            Palette: One FamilyCatalog per family; the advanced blocks when ``full``.
        """
        # 1. The families every consumer needs (node cards: labels, config schema, I/O). A shared
        #    family is scoped to this pipeline kind's own kinds via the FAMILY_KINDS allowlist.
        families = [
            FamilyCatalog.from_family(family, cls.FAMILY_KINDS.get(family))
            for family in cls.FAMILIES
            if family in NodeRegistry.families()
        ]
        if not full:
            return Palette(families=families)

        # 2. The advanced blocks — the graph-editing vocabulary, described on demand only.
        return Palette(
            families=families,
            run_inputs=list(cls.RUN_INPUTS),
            mechanics=GraphMechanics.describe(),
            artefacts=ArtefactCatalog.describe(),
        )

    @classmethod
    def default_blob(cls) -> GroupNodeBlob:
        """
        The stock search pipeline — the blob a new collection's search editor opens on.

        The minimal P1 graph: normalize the query → encode it with the collection's embedder →
        retrieve a hybrid candidate pool → hydrate + rank the hits → deliver the SearchResult. A
        single linear OnSuccess chain; the fuse/rerank/post-process stages join as later phases.

        Returns:
            GroupNodeBlob: The serialised default topology (nodes, transitions, bindings).
        """
        # 1. The five nodes of the smallest viable search graph (empty config = every default).
        nodes = [
            ActionNodeBlob(id="normalize", family="query", kind="normalize"),
            ActionNodeBlob(id="encode", family="encode", kind="collection"),
            ActionNodeBlob(id="retrieve", family="retrieve", kind="hybrid"),
            ActionNodeBlob(id="hydrate", family="postprocess", kind="hydrate"),
            ActionNodeBlob(id="deliver", family="deliver", kind="hits"),
        ]

        # 2. The linear control flow (OnSuccess is the Transition default).
        transitions = [
            Transition(from_node_id="normalize", to_node_id="encode"),
            Transition(from_node_id="encode", to_node_id="retrieve"),
            Transition(from_node_id="retrieve", to_node_id="hydrate"),
            Transition(from_node_id="hydrate", to_node_id="deliver"),
        ]

        # 3. The data wiring — run inputs at the edges, node-to-node along the spine.
        bindings = {
            "normalize": {
                "query": FromRunInput(field_name="query"),
                "filters": FromRunInput(field_name="filters"),
            },
            "encode": {
                "spec": FromNode(node_id="normalize", field_name="spec"),
                "contract": FromRunInput(field_name="contract"),
            },
            "retrieve": {
                "spec": FromNode(node_id="normalize", field_name="spec"),
                "encoded": FromNode(node_id="encode", field_name="encoded"),
            },
            "hydrate": {
                "candidates": FromNode(node_id="retrieve", field_name="candidates"),
                "spec": FromNode(node_id="normalize", field_name="spec"),
            },
            "deliver": {
                "ranked": FromNode(node_id="hydrate", field_name="ranked"),
                "query": FromRunInput(field_name="query"),
            },
        }
        return GroupNodeBlob(
            id="search_pipeline", nodes=nodes, transitions=transitions, bindings=bindings
        )


__all__ = ["SearchPipeline"]
