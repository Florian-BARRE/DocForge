# ====== Code Summary ======
# The CANONICAL SKELETON of the ingestion pipeline expressed as an ordered list of stages — the
# fixed SHAPE the product view is built on. Each StageMeta declares a stage's identity (key, title,
# description), how the user interacts with it (StageKind), whether it can be toggled off
# (removable), the family it draws providers from, its primary config node, and the stages it
# depends on (requires). This table is the single source of truth shared by the assembler (state →
# blob), the reader (blob → state) and the viewer (state → catalog): rename a stage here and every
# side follows. FIGURE_BRANCHES fixes the per-class model-call sites of the enrich loop (the chain
# slots): scanned text is read by an OCR chain, the visual classes by a VLM chain.

# ====== Standard Library Imports ======
from dataclasses import dataclass, field
from enum import StrEnum

# ====== Internal Project Imports ======
from shared_libs.public_models import FIGURE_ROUTING


class StageKind(StrEnum):
    """
    How the user interacts with a stage — what editor face the UI renders for it.

    Attributes:
        FIXED: Always on, no choice (intake, parse, deliver) — structural plumbing.
        TOGGLE: An optional stage with a single implementation, switched on/off (render, enrich,
            the two metagen scopes, embed).
        PROVIDER: An exclusive family — pick THE provider among the family's kinds (chunk).
        STACK: An ordered stack of stackable methods the user composes (contextualize).
    """

    FIXED = "fixed"
    TOGGLE = "toggle"
    PROVIDER = "provider"
    STACK = "stack"


class StageKey(StrEnum):
    """The stable key of every stage of the canonical ingestion skeleton, in run order."""

    INTAKE = "intake"
    PARSE = "parse"
    RENDER = "render"
    ENRICH = "enrich"
    CHUNK = "chunk"
    CONTEXTUALIZE = "contextualize"
    METAGEN_CHUNK = "metagen_chunk"
    METAGEN_DOCUMENT = "metagen_document"
    EMBED = "embed"
    DELIVER = "deliver"


@dataclass(frozen=True)
class StageMeta:
    """
    The immutable description of one stage of the canonical skeleton.

    Attributes:
        key (StageKey): Stable stage identifier.
        title (str): Human label surfaced in the UI.
        description (str): What the stage does, in one or two sentences.
        kind (StageKind): The interaction face (fixed / toggle / provider / stack).
        removable (bool): Whether the stage can be toggled off (fixed stages are False).
        family (str | None): The registry family the stage draws its node(s) from, when single.
        primary_node (str | None): Id of the stage's main config-bearing node (None for
            composite / stack stages whose config is edited elsewhere).
        requires (tuple[str, ...]): Keys of the stages this one depends on (enabling it enables
            them; disabling them cascades to this one).
    """

    key: StageKey
    title: str
    description: str
    kind: StageKind
    removable: bool
    family: str | None = None
    primary_node: str | None = None
    requires: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class FigureBranch:
    """
    One per-class branch of the enrich loop — a fixed model-call site the user builds a chain for.

    Attributes:
        figure_kind (str): The FigureKind value the classifier routes on (when_equals).
        slot (str): The chain slot key exposed to the UI (e.g. ``scanned_text_ocr``).
        family (str): The model family the branch calls (``ocr`` or ``vlm``).
        title (str): Human label of the branch.
        description (str): What the branch is for.
    """

    figure_kind: str
    slot: str
    family: str
    title: str
    description: str


def _figure_branches() -> tuple[FigureBranch, ...]:
    """
    Derive the enrich branch table from the figure routing — one branch per non-decorative class.

    The chain slot follows the fixed ``<class>_<family>`` convention (e.g. scanned_text + ocr →
    ``scanned_text_ocr``), so the studio slot key stays a stage-layer concern derived from the
    shared taxonomy rather than a hand-authored literal.

    Returns:
        tuple[FigureBranch, ...]: One branch per enriched FigureKind, in routing-table order.
    """
    branches: list[FigureBranch] = []
    for kind, routing in FIGURE_ROUTING.items():
        if routing.family is None:  # decorative → no branch, handled by the skip terminal.
            continue
        branches.append(
            FigureBranch(
                figure_kind=kind.value,
                slot=f"{kind.value}_{routing.family}",
                family=routing.family,
                title=routing.title,
                description=routing.description,
            )
        )
    return tuple(branches)


def _decorative_kinds() -> tuple[str, ...]:
    """Return the figure classes routed to the zero-spend skip terminal (no chain, no model)."""
    return tuple(kind.value for kind, routing in FIGURE_ROUTING.items() if routing.decorative)


class StageSpecs:
    """Static access to the canonical stage skeleton and the enrich branch table."""

    def __new__(cls, *args: object, **kwargs: object) -> None:
        raise TypeError("StageSpecs is a static-only class and cannot be instantiated.")

    # The ordered skeleton — the UI renders exactly this vertical rail, greying disabled stages.
    ORDER: tuple[StageMeta, ...] = (
        StageMeta(
            key=StageKey.INTAKE, kind=StageKind.FIXED, removable=False,
            title="Intake",
            description="Validate the upload against the collection contract and prepare a PDF "
            "view (format probe, admission gate, conversion, PDF probe, content addressing).",
        ),
        StageMeta(
            key=StageKey.PARSE, kind=StageKind.PROVIDER, removable=False,
            family="parser", primary_node="parse",
            title="Parse",
            description="Turn the PDF into the canonical document IR (blocks, tables, figures, "
            "heading tree) with the chosen parser.",
        ),
        StageMeta(
            key=StageKey.RENDER, kind=StageKind.TOGGLE, removable=True,
            family="render", primary_node="figures",
            title="Render figures",
            description="Rasterise the pages and embed each figure's crop into the IR so the "
            "enrichment can read and describe them.",
        ),
        StageMeta(
            key=StageKey.ENRICH, kind=StageKind.TOGGLE, removable=True,
            family="enrich", primary_node="classify", requires=("render",),
            title="Enrich figures",
            description="Per figure: classify it, then read scanned text (OCR chain) or describe "
            "charts/diagrams/photos (VLM chain), and fold the result back into the IR.",
        ),
        StageMeta(
            key=StageKey.CHUNK, kind=StageKind.PROVIDER, removable=False,
            family="chunker", primary_node="chunk",
            title="Chunk",
            description="Split the enriched IR into retrieval chunks with the chosen chunking "
            "method (structure-aware, fixed-size, semantic).",
        ),
        StageMeta(
            key=StageKey.CONTEXTUALIZE, kind=StageKind.STACK, removable=False,
            family="contextualize",
            title="Contextualize",
            description="Grow each chunk's search context with an ordered stack of methods "
            "(document metadata, breadcrumb, sliding window, LLM) — the order is the prefix order.",
        ),
        StageMeta(
            key=StageKey.METAGEN_CHUNK, kind=StageKind.TOGGLE, removable=True,
            family="metagen", primary_node="meta_chunk",
            title="Chunk metadata",
            description="Fill the contract's generated chunk-scope fields with an LLM, one "
            "structured generation per chunk.",
        ),
        StageMeta(
            key=StageKey.METAGEN_DOCUMENT, kind=StageKind.TOGGLE, removable=True,
            family="metagen", primary_node="meta_doc",
            title="Document metadata",
            description="Fill the contract's generated document-scope fields with an LLM from a "
            "view of the document.",
        ),
        StageMeta(
            key=StageKey.EMBED, kind=StageKind.PROVIDER, removable=True,
            family="embed", primary_node="embed",
            title="Embed",
            description="Vectorise every chunk (dense + sparse) with the chosen embedder — "
            "disable it to index no vectors.",
        ),
        StageMeta(
            key=StageKey.DELIVER, kind=StageKind.FIXED, removable=False,
            family="deliver", primary_node="bundle",
            title="Deliver",
            description="Assemble everything the run produced into the output bundle the worker "
            "persists.",
        ),
    )

    # The fixed model-call sites of the enrich loop — one chain slot per figure class, DERIVED from
    # the single-source figure routing (decorative classes have no chain: they are a zero-spend
    # skip). Adding a FigureKind updates FIGURE_ROUTING once and this table follows.
    FIGURE_BRANCHES: tuple[FigureBranch, ...] = _figure_branches()

    # The figure classes routed to the zero-spend skip terminal (no chain, no model), derived from
    # the same single source — every class here is a decorative kind of the routing table.
    DECORATIVE_KINDS: tuple[str, ...] = _decorative_kinds()

    @classmethod
    def meta(cls, key: str) -> StageMeta:
        """Return the StageMeta of a stage key (raises KeyError when the key is unknown)."""
        for stage in cls.ORDER:
            if stage.key == key:
                return stage
        raise KeyError(f"unknown stage '{key}'")

    @classmethod
    def branch(cls, slot: str) -> FigureBranch:
        """Return the enrich branch owning a chain slot (raises KeyError when unknown)."""
        for branch in cls.FIGURE_BRANCHES:
            if branch.slot == slot:
                return branch
        raise KeyError(f"unknown chain slot '{slot}'")


__all__ = ["StageKind", "StageKey", "StageMeta", "FigureBranch", "StageSpecs"]
