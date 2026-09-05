"""Palette scoping is ENFORCED at the write boundary, not merely advisory.

Each pipeline kind is assembled from a fixed set of families (its FAMILIES + the FAMILY_KINDS
allowlist for shared families). A blob may only contain kinds that pipeline's palette actually
offers — including the SELECTABLE=False internal wiring the stage builder emits, but NOT a foreign
kind (a search kind in an ingest graph, or vice-versa). These tests pin the ``PaletteScopeValidator``
rule and its enforcement through the shared, CONTEXT-free ``BlobStructureValidator``.
"""

import pytest

from shared_libs.pipelines.base import ActionNode, ForEach, Group
from shared_libs.pipelines.build import PipelineBuilder
from shared_libs.pipelines.build.blob import ActionNodeBlob, GroupNodeBlob
from shared_libs.pipelines.ingest import IngestPipeline
from shared_libs.pipelines.registry import NodeRegistry
from shared_libs.pipelines.search import SearchPipeline
from shared_libs.pipelines.validation import (
    BlobStructureValidator,
    BlobValidationError,
    PaletteScopeValidator,
    ValidationCode,
)


@pytest.fixture(scope="module")
def builder() -> PipelineBuilder:
    """A stateless builder shared by the module's build-then-scope assertions."""
    return PipelineBuilder()


# --------------------------------------------------------------------------- #
# resolve(): the allowed set scopes shared families and admits wiring kinds.
# --------------------------------------------------------------------------- #
def test_resolve_scopes_shared_deliver_family_per_pipeline() -> None:
    """The shared ``deliver`` family is scoped to each pipeline's own terminal kind."""
    ingest_allowed = IngestPipeline.allowed_kinds()
    search_allowed = SearchPipeline.allowed_kinds()

    assert ingest_allowed["deliver"] == {"bundle"}
    assert search_allowed["deliver"] == {"hits"}
    # The two pipelines share only the deliver family, and never each other's kinds.
    assert "hits" not in {k for kinds in ingest_allowed.values() for k in kinds}
    assert "bundle" not in {k for kinds in search_allowed.values() for k in kinds}


def test_resolve_admits_non_selectable_wiring_kinds() -> None:
    """An unscoped family's allowed set includes its internal wiring, not just palette cards."""
    allowed = IngestPipeline.allowed_kinds()
    selectable = {card.kind for card in NodeRegistry.catalog("metagen")}
    registered = set(NodeRegistry.kinds("metagen"))

    # metagen carries SELECTABLE=False wiring (chunk_prep/chunk_apply/...): registered > selectable.
    assert registered > selectable
    assert allowed["metagen"] == registered
    assert {"chunk_prep", "chunk_apply"} <= allowed["metagen"]


# --------------------------------------------------------------------------- #
# validate(): a valid built graph is clean; a foreign kind is flagged.
# --------------------------------------------------------------------------- #
def _built_kinds(group: Group) -> set[str]:
    """Every action-node KIND in a built graph (nested groups and foreach bodies included)."""
    kinds: set[str] = set()

    def walk(g: Group) -> None:
        for child in g.children:
            if isinstance(child, ActionNode):
                kinds.add(child.KIND)
            elif isinstance(child, Group):
                walk(child)
            elif isinstance(child, ForEach):
                walk(child.body)

    walk(group)
    return kinds


@pytest.mark.parametrize(
    "blob_factory",
    [IngestPipeline.default_blob, IngestPipeline.light_blob],
)
def test_default_ingest_blobs_are_palette_clean(builder, blob_factory) -> None:
    """The stock and light ingestion topologies contain only palette kinds (the subset property)."""
    group = builder.build(blob_factory().model_dump())
    allowed = IngestPipeline.allowed_kinds()

    # No foreign kind, AND every built kind is in the allowed set (the guard's core invariant).
    assert PaletteScopeValidator.validate(group, allowed) == []
    allowed_flat = {kind for kinds in allowed.values() for kind in kinds}
    assert _built_kinds(group) <= allowed_flat


@pytest.mark.parametrize(
    "blob_factory",
    [
        SearchPipeline.default_blob,
        SearchPipeline.rerank_blob,
        SearchPipeline.rewrite_blob,
        SearchPipeline.hyde_blob,
    ],
)
def test_default_search_blobs_are_palette_clean(builder, blob_factory) -> None:
    """Every stock search topology contains only search-palette kinds."""
    group = builder.build(blob_factory().model_dump())
    assert PaletteScopeValidator.validate(group, SearchPipeline.allowed_kinds()) == []


def test_non_selectable_wiring_kind_is_admitted(builder) -> None:
    """A built graph carrying a SELECTABLE=False wiring kind is NOT rejected as foreign.

    ``keep_raw`` is a contextualize fail-soft terminal the stage builder emits, hidden from the
    palette picker (``catalog``) but legitimately present in a valid built graph — so the allowed
    set must admit it. This proves the guard scopes to "every registered kind of the pipeline's
    families", not merely the selectable palette cards (which would wrongly reject the scaffolding).
    """
    # 1. keep_raw is genuinely internal wiring — non-selectable, absent from the palette picker.
    assert NodeRegistry.get("contextualize", "keep_raw").describe().selectable is False
    assert "keep_raw" not in {card.kind for card in NodeRegistry.catalog("contextualize")}

    # 2. A graph built with it is palette-clean under the ingestion scope.
    blob = GroupNodeBlob(
        id="wiring_probe",
        nodes=[ActionNodeBlob(id="kr", family="contextualize", kind="keep_raw", config={})],
    )
    group = builder.build(blob.model_dump())
    assert PaletteScopeValidator.validate(group, IngestPipeline.allowed_kinds()) == []


def test_search_kind_in_ingest_graph_is_flagged(builder) -> None:
    """A search topology validated under the INGEST palette is rejected as foreign."""
    group = builder.build(SearchPipeline.default_blob().model_dump())
    issues = PaletteScopeValidator.validate(group, IngestPipeline.allowed_kinds())

    assert issues, "a search graph must not be palette-clean under the ingest scope"
    assert all(issue.code is ValidationCode.KIND_NOT_IN_PALETTE for issue in issues)


def test_ingest_kind_in_search_graph_is_flagged(builder) -> None:
    """An ingest topology validated under the SEARCH palette is rejected as foreign."""
    group = builder.build(IngestPipeline.default_blob().model_dump())
    issues = PaletteScopeValidator.validate(group, SearchPipeline.allowed_kinds())

    assert issues
    assert all(issue.code is ValidationCode.KIND_NOT_IN_PALETTE for issue in issues)


# --------------------------------------------------------------------------- #
# BlobStructureValidator: the shared write/import boundary enforces the scope.
# --------------------------------------------------------------------------- #
def test_blob_validator_accepts_own_pipeline_blobs() -> None:
    """A legitimate ingest blob and search blob both pass their own scoped validation."""
    validator = BlobStructureValidator()
    validator.validate_ingest(IngestPipeline.default_blob().model_dump())
    validator.validate_ingest(IngestPipeline.light_blob().model_dump())
    validator.validate_search(SearchPipeline.default_blob().model_dump())
    validator.validate_search(SearchPipeline.rerank_blob().model_dump())


def test_blob_validator_rejects_search_blob_as_ingest() -> None:
    """A search blob written to the ingest slot is a fail-fast palette rejection."""
    validator = BlobStructureValidator()
    with pytest.raises(BlobValidationError) as exc:
        validator.validate_ingest(SearchPipeline.default_blob().model_dump())

    assert any(i.code is ValidationCode.KIND_NOT_IN_PALETTE for i in exc.value.issues)


def test_blob_validator_rejects_ingest_blob_as_search() -> None:
    """An ingest blob written to the search slot is a fail-fast palette rejection."""
    validator = BlobStructureValidator()
    with pytest.raises(BlobValidationError) as exc:
        validator.validate_search(IngestPipeline.default_blob().model_dump())

    assert any(i.code is ValidationCode.KIND_NOT_IN_PALETTE for i in exc.value.issues)
