# ====== Code Summary ======
# Future query-transform methods, registered as SELECTABLE=False placeholders: they appear in the
# registry (so the taxonomy is discoverable and the artefact wiring is future-ready) but never in a
# built graph, so their run() bodies raise. Each carries a correct family/kind + typed, described
# I/O slots so it validates like any registered node. Bodies land phase by phase (research P4).

# ====== Third-Party Library Imports ======
from pydantic import Field

# ====== Internal Project Imports ======
from shared_libs.pipelines.base import NodeConfig, NodeInput, NodeOutput
from shared_libs.pipelines.registry import NodeRegistry
from shared_libs.public_models.search import QuerySpec, RawQuery

# ====== Local Project Imports ======
from ..placeholder import PlaceholderNode


class _QueryPlaceholderConfig(NodeConfig):
    """Knob-less config shared by the query-transform placeholders."""


class _FromRawQuery(NodeInput):
    """Consumes the caller's raw query."""

    query: RawQuery = Field(description="The caller's raw query to interpret/transform.")


class _FromQuerySpec(NodeInput):
    """Consumes a normalised QuerySpec."""

    spec: QuerySpec = Field(description="The normalised query to transform.")


class _OneQuerySpec(NodeOutput):
    """Produces one transformed QuerySpec."""

    spec: QuerySpec = Field(description="The transformed query.")


class _ManyQuerySpecs(NodeOutput):
    """Produces N query variants (fanned out by a ForEach downstream)."""

    specs: list[QuerySpec] = Field(
        default_factory=list, description="The query variants to fan out over."
    )


@NodeRegistry.register("query")
class QueryUnderstandNode(PlaceholderNode):
    """LLM intent + filter extraction from the raw query (future)."""

    KIND = "understand"
    NAME = "Understand query"
    SUMMARY = "LLM intent classification + structured filter extraction from the raw query."
    Config = _QueryPlaceholderConfig
    Consumes = _FromRawQuery
    Produces = _OneQuerySpec


@NodeRegistry.register("query")
class QueryMultiNode(PlaceholderNode):
    """Expand one query into N sub-query variants for a ForEach fan-out (future)."""

    KIND = "multi"
    NAME = "Multi-query"
    SUMMARY = "Expand the query into N variants, fanned out over retrieval via a ForEach."
    Config = _QueryPlaceholderConfig
    Consumes = _FromQuerySpec
    Produces = _ManyQuerySpecs


__all__ = ["QueryUnderstandNode", "QueryMultiNode"]
