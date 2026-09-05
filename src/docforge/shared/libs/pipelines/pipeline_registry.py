# ====== Code Summary ======
# PipelineRegistry — the single source of truth for WHICH pipeline kinds exist (ingest, search) and
# the facade class behind each. Every pipeline facade (IngestPipeline, SearchPipeline) exposes the
# same two class methods the design surface needs — palette(full) and default_blob() — so the
# router can iterate this registry instead of hardcoding one ingest surface. Importing this module
# imports both facades, which registers their node families.
#
# NOTE: this maps pipeline KINDS (ingest, search) to their facades — a different concern from the
# introspection catalogue, which builds the palette of node kinds within a single pipeline.

# ====== Standard Library Imports ======
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

# ====== Internal Project Imports ======
from shared_libs.pipelines.build import GroupNodeBlob
from shared_libs.pipelines.ingest import IngestPipeline
from shared_libs.pipelines.introspection import Palette
from shared_libs.pipelines.search import SearchPipeline


@runtime_checkable
class PipelineFacade(Protocol):
    """The static contract every pipeline facade satisfies — its palette and its default topology."""

    @classmethod
    def palette(cls, full: bool = False) -> Palette:
        """Return the UI palette of this pipeline (lean by default, advanced blocks when ``full``)."""
        ...

    @classmethod
    def default_blob(cls) -> GroupNodeBlob:
        """Return the stock topology a new editor opens on."""
        ...


@dataclass(frozen=True)
class PipelineSpec:
    """
    One discoverable pipeline kind — its identity, its facade, and whether it has a stage rail.

    Attributes:
        key (str): Stable pipeline identifier used in the URL (e.g. ``"ingest"``, ``"search"``).
        title (str): Human label surfaced in the discovery index.
        description (str): What this pipeline does.
        facade (type[PipelineFacade]): The facade class exposing palette() + default_blob().
        supports_stages (bool): True when the pipeline has a stage-rail surface (view/apply). The
            stage layer is ingest-coupled today; search is advanced/headless-only, so it is False.
    """

    key: str
    title: str
    description: str
    facade: type[PipelineFacade]
    supports_stages: bool


class PipelineRegistry:
    """Static registry of the pipeline kinds the backend serves — the second-pipeline-kind seam."""

    # The ordered set of pipeline surfaces. Adding a pipeline kind is a single entry here — the
    # router, the discovery index and any runner selection derive from this one list.
    _SPECS: tuple[PipelineSpec, ...] = (
        PipelineSpec(
            key="ingest",
            title="Ingestion pipeline",
            description=(
                "Document intake to indexed chunks: intake, parse, per-figure enrichment, "
                "chunking, contextualization, metadata generation and embedding."
            ),
            facade=IngestPipeline,
            supports_stages=True,
        ),
        PipelineSpec(
            key="search",
            title="Search pipeline",
            description=(
                "Query to ranked hits: query normalization, collection encoding, hybrid retrieval, "
                "hydration and delivery — the retrieval analog of the ingestion pipeline."
            ),
            facade=SearchPipeline,
            supports_stages=False,
        ),
    )

    def __new__(cls, *args: object, **kwargs: object) -> None:
        raise TypeError("PipelineRegistry is a static-only class and cannot be instantiated.")

    @classmethod
    def specs(cls) -> tuple[PipelineSpec, ...]:
        """
        Every registered pipeline surface, in discovery order.

        Returns:
            tuple[PipelineSpec, ...]: The pipeline specs the router iterates.
        """
        return cls._SPECS

    @classmethod
    def keys(cls) -> list[str]:
        """
        The registered pipeline keys.

        Returns:
            list[str]: Every pipeline key (e.g. ``["ingest", "search"]``).
        """
        return [spec.key for spec in cls._SPECS]

    @classmethod
    def get(cls, key: str) -> PipelineSpec | None:
        """
        Resolve a pipeline spec by key.

        Args:
            key (str): The pipeline key to look up.

        Returns:
            PipelineSpec | None: The matching spec, or None when the key is unknown.
        """
        # 1. Linear scan — the set of pipeline kinds is tiny and fixed.
        for spec in cls._SPECS:
            if spec.key == key:
                return spec
        return None


__all__ = ["PipelineRegistry", "PipelineSpec", "PipelineFacade"]
