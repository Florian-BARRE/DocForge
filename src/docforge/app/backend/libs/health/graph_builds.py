# ====== Code Summary ======
# CollectionGraphBuilder — builds a collection's two graphs (ingest, search) for the health probe,
# capturing a build/validation failure as a message instead of letting it crash the endpoint. It
# reuses the EXACT healing + build path the worker/search runner use (BlobNormalizer.normalize for
# ingest, the stored-or-stock resolve for search, then PipelineBuilder + GraphValidator), so "does
# this collection build?" is answered identically to a real run — a collection with an unbuildable
# blob yields ``buildable=false`` + the error, never a 500.

# ====== Standard Library Imports ======
from dataclasses import dataclass

# ====== Third-Party Library Imports ======
from loggerplusplus import loggerplusplus

# ====== Internal Project Imports ======
from shared_libs.pipelines.base import Group
from shared_libs.pipelines.build import PipelineBuilder
from shared_libs.pipelines.ingest import BlobNormalizer
from shared_libs.pipelines.search import SearchPipeline
from shared_libs.pipelines.validation import GraphValidator, ValidationIssue


@dataclass(slots=True)
class GraphBuildOutcome:
    """The result of building one graph for the health probe: the group, or the failure message."""

    group: Group | None
    error: str | None

    @property
    def buildable(self) -> bool:
        """Whether the graph built and structurally validated (a group, no error)."""
        return self.group is not None and self.error is None


class CollectionGraphBuilder:
    """Static builder of a collection's ingest + search graphs, failure-captured for the probe."""

    logger = loggerplusplus.bind(identifier="CollectionGraphBuilder")

    def __new__(cls, *args: object, **kwargs: object) -> None:
        raise TypeError("CollectionGraphBuilder is a static-only class and cannot be instantiated.")

    @staticmethod
    def __format_issues(issues: list[ValidationIssue]) -> str:
        """Join structural validation issues into one human-readable line."""
        return "; ".join(f"[{issue.code}] {issue.location}: {issue.message}" for issue in issues)

    @classmethod
    def build_ingest(
        cls, builder: PipelineBuilder, validator: GraphValidator, stored_blob: dict
    ) -> GraphBuildOutcome:
        """
        Heal + build + validate the collection's ingest graph (the worker's exact path).

        Args:
            builder (PipelineBuilder): The shared graph builder.
            validator (GraphValidator): The shared structural validator.
            stored_blob (dict): The collection's stored pipeline blob.

        Returns:
            GraphBuildOutcome: The built group, or ``group=None`` + the captured error message.
        """
        # 1. Heal to the current engine, build, then structurally validate — any step may fail; a
        #    failure is the honest "unbuildable" signal, captured as a message, never re-raised.
        try:
            normalized = BlobNormalizer.normalize(stored_blob)
            group = builder.build(normalized)
            issues = validator.validate(group)
        except Exception as exc:  # noqa: BLE001 — every build failure is a reportable "not buildable".
            return GraphBuildOutcome(group=None, error=f"{type(exc).__name__}: {exc}")
        if issues:
            return GraphBuildOutcome(group=None, error=cls.__format_issues(issues))
        return GraphBuildOutcome(group=group, error=None)

    @classmethod
    def build_search(
        cls, builder: PipelineBuilder, validator: GraphValidator, search_blob: dict | None
    ) -> GraphBuildOutcome:
        """
        Resolve (stored-or-stock) + build + validate the search graph (the search runner's path).

        Args:
            builder (PipelineBuilder): The shared graph builder.
            validator (GraphValidator): The shared structural validator.
            search_blob (dict | None): The collection's stored search blob ({} / None = stock default).

        Returns:
            GraphBuildOutcome: The built group, or ``group=None`` + the captured error message.
        """
        # 1. The collection's own topology (has "nodes") wins; else the product's stock default.
        stored = search_blob or {}
        resolved = (
            stored if stored.get("nodes") else SearchPipeline.default_blob().model_dump(mode="json")
        )
        # 2. Build + validate; a broken stored search blob is a captured error, not a crash.
        try:
            group = builder.build(resolved)
            issues = validator.validate(group)
        except Exception as exc:  # noqa: BLE001 — every build failure is a reportable "not buildable".
            return GraphBuildOutcome(group=None, error=f"{type(exc).__name__}: {exc}")
        if issues:
            return GraphBuildOutcome(group=None, error=cls.__format_issues(issues))
        return GraphBuildOutcome(group=group, error=None)


__all__ = ["CollectionGraphBuilder", "GraphBuildOutcome"]
