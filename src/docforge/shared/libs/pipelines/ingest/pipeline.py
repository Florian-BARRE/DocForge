# ====== Code Summary ======
# IngestPipeline — the class that TIES the ingestion pipeline together: it declares which node
# families compose it (its dedicated nodes + the generic capability families it uses), triggers
# their registration, is the origin of the DESCRIBE the UI is populated from (the palette of
# every block available to assemble an ingestion pipeline), and carries the default topology
# (default_blob / light_blob) a new collection's editor opens on.

# ====== Internal Project Imports ======
import shared_libs.pipelines.ingest.nodes  # noqa: F401 — registers the dedicated nodes
import shared_libs.pipelines.nodes  # noqa: F401 — registers the generic capability families
from shared_libs.pipelines.base import IoSlot
from shared_libs.pipelines.build import GroupNodeBlob
from shared_libs.pipelines.introspection import (
    ArtefactCatalog,
    FamilyCatalog,
    GraphMechanics,
    Palette,
    PipelinePreset,
)
from shared_libs.pipelines.registry import NodeRegistry
from shared_libs.pipelines.validation import PaletteScopeValidator

# ====== Local Project Imports ======
from .stages import (
    IngestAssembler,
    StageAction,
    default_state,
    high_precision_state,
    light_state,
    ocr_scan_state,
)


class IngestPipeline:
    """Static entry point of the ingestion pipeline — its families, its palette, its topology."""

    # The families an ingestion pipeline is assembled from: its DEDICATED stage families first
    # (intake…metagen, plus the shared deliver terminal), then the GENERIC capability families its
    # enrichment relies on (embed, ocr, vlm, llm, structgen).
    FAMILIES = (
        "intake",
        "converter",
        "parser",
        "docmeta",
        "render",
        "enrich",
        "chunker",
        "contextualize",
        "metagen",
        "embed",
        "deliver",
        "ocr",
        "vlm",
        "llm",
        "structgen",
    )

    # Per-family kind allowlist for SHARED families: ``deliver`` is reused by search, so its palette
    # view must be scoped to ingestion's own terminal kind (``bundle``) — otherwise search's
    # ``hits`` would leak into the ingestion palette. Exclusive families stay unrestricted.
    FAMILY_KINDS: dict[str, set[str]] = {"deliver": {"bundle"}}

    # The artefacts the RUN hands to the graph — the sources a FromRunInput binding can target.
    # Declared here (not guessed by the UI) so the entry wiring stays backend-described.
    RUN_INPUTS = (
        IoSlot(
            name="source",
            artefact_type="SourceDocument",
            description="The uploaded document: filename, raw bytes and declared metadata.",
        ),
        IoSlot(
            name="contract",
            artefact_type="CollectionContract",
            description=(
                "The target collection's contract: accepted formats, size cap and metadata "
                "schema the run is admitted against."
            ),
        ),
    )

    def __new__(cls, *args: object, **kwargs: object) -> None:
        raise TypeError("IngestPipeline is a static-only class and cannot be instantiated.")

    @classmethod
    def palette(cls, full: bool = False) -> Palette:
        """
        The UI palette of the ingestion pipeline — every block available to assemble it.

        The default palette carries only the families (each node with its full describe()
        card) — all the product stage rail needs. The FULL palette adds the graph-level
        vocabulary (run inputs, mechanics, artefacts) for the advanced, headless design
        surface — computed only on demand so the common payload stays lean.

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
            mechanics=GraphMechanics.describe(stage_actions=StageAction),
            artefacts=ArtefactCatalog.describe(),
        )

    @classmethod
    def allowed_kinds(cls) -> dict[str, set[str]]:
        """
        The (family → kinds) map a valid built ingestion graph may use — the palette scope.

        Resolved from ``FAMILIES`` (the families ingestion is built from) and ``FAMILY_KINDS`` (the
        per-family scoping for shared families). It deliberately admits the ``SELECTABLE=False``
        internal wiring kinds a stage builder emits, so a valid built graph is never rejected for
        its own scaffolding. Fed to ``PaletteScopeValidator`` at the write boundary.

        Returns:
            dict[str, set[str]]: Family → the set of kinds an ingestion graph may contain.
        """
        return PaletteScopeValidator.resolve(cls.FAMILIES, cls.FAMILY_KINDS)

    @classmethod
    def default_blob(cls) -> GroupNodeBlob:
        """
        The stock ingestion pipeline — the blob a new collection's editor opens on.

        Covers every built stage: intake → parse → render → enrich (the per-figure loop with its
        per-class model chains: a cheap→robust OCR chain for scanned text, a VLM per visual class) →
        chunk → contextualize (the zero-cost stack doc_meta → breadcrumb) → chunk/document metagen →
        embed → deliver. This is the SINGLE canonical skeleton: it is assembled from the default
        stage state, and the stage compiler re-uses the very same assembler to re-wire the graph
        when a stage is toggled — so the two views can never drift.

        Returns:
            GroupNodeBlob: The serialised default topology (nodes, transitions, bindings).
        """
        return IngestAssembler.assemble(default_state())

    @classmethod
    def light_blob(cls) -> GroupNodeBlob:
        """
        The LIGHT ingestion pipeline — a fast, local, free retrieval core.

        Same stock skeleton as ``default_blob`` with every ENRICHMENT stage off (figure enrich,
        the contextualize stack, chunk + document metagen), leaving intake → parse → chunk → embed
        → deliver. Assembled through the very same assembler, so it enjoys the identical
        "always builds" guarantee and passes the graph validator. Offered as a creation preset for
        collections that want cheap searchable vectors without any provider-hosted enrichment.

        Returns:
            GroupNodeBlob: The serialised light topology (nodes, transitions, bindings).
        """
        return IngestAssembler.assemble(light_state())

    @classmethod
    def ocr_scan_blob(cls) -> GroupNodeBlob:
        """
        The OCR-SCAN ingestion pipeline — a local OCR pass for scanned / image-only documents.

        The stock skeleton with the per-figure enrich stage ON in uniform ``ocr`` mode, wired to a
        LOCAL RapidOCR chain (no provider-hosted escalation), so a scanned corpus is read into
        searchable text with zero external configuration. Assembled through the very same assembler,
        so it enjoys the identical "always builds" guarantee and passes the graph validator.

        Returns:
            GroupNodeBlob: The serialised OCR-scan topology (nodes, transitions, bindings).
        """
        return IngestAssembler.assemble(ocr_scan_state())

    @classmethod
    def high_precision_blob(cls) -> GroupNodeBlob:
        """
        The HIGH-PRECISION ingestion pipeline — finer chunks for sharper hybrid retrieval.

        The stock skeleton with the structure-aware chunker tightened to smaller units (target 256 /
        max 512 tokens, overlap 96); the local contextualize stack and the dense+sparse embed the
        default ships keep it hybrid-ready. Assembled through the very same assembler.

        Returns:
            GroupNodeBlob: The serialised high-precision topology (nodes, transitions, bindings).
        """
        return IngestAssembler.assemble(high_precision_state())

    # The creation presets this pipeline offers — each a curated, validation-passing stock blob (a
    # starting point, NOT a new engine). The first entry is the default a collection gets when no
    # preset is selected. All keep every provider-hosted stage OFF, so each is preflight-clean.
    _PRESETS: tuple[tuple[str, str, str, bool], ...] = (
        (
            "standard",
            "Standard",
            "The full stock pipeline: intake, parse, local contextualization and dense+sparse "
            "embedding. Figure enrichment and metadata generation ship off (provider-hosted) — "
            "opt them in per collection. The balanced default for most corpora.",
            True,
        ),
        (
            "light",
            "Light (fast, local, free)",
            "The cheapest searchable core: intake, parse, chunk and embed only — no figure "
            "enrichment, contextualization or metadata generation. Pick it for the fastest, fully "
            "local path to vectors.",
            False,
        ),
        (
            "ocr_scan",
            "OCR scan",
            "For scanned or image-only documents: the stock pipeline with a LOCAL OCR pass (uniform "
            "RapidOCR) over every figure, so full-page scans become searchable text. Still fully "
            "local and free — no provider-hosted enrichment.",
            False,
        ),
        (
            "high_precision",
            "High precision",
            "Finer, more focused chunks (smaller target size, more overlap) over the stock pipeline "
            "for sharper hybrid retrieval — hybrid-ready out of the box (dense + sparse). Costs more "
            "vectors per document.",
            False,
        ),
    )

    # name -> the builder method that assembles its stock blob (resolved server-side, not UI-sent).
    _PRESET_BLOBS: dict[str, str] = {
        "standard": "default_blob",
        "light": "light_blob",
        "ocr_scan": "ocr_scan_blob",
        "high_precision": "high_precision_blob",
    }

    @classmethod
    def presets(cls) -> list[PipelinePreset]:
        """
        The discoverable creation presets of the ingestion pipeline (name + label + rationale).

        Carries only the metadata a schema-driven UI / the MCP needs to OFFER the choice — the blob
        each selects is resolved server-side by ``preset_blob``. The default preset is flagged.

        Returns:
            list[PipelinePreset]: One entry per offered preset, in display order.
        """
        return [
            PipelinePreset(name=name, label=label, description=description, is_default=is_default)
            for name, label, description, is_default in cls._PRESETS
        ]

    @classmethod
    def preset_blob(cls, preset: str | None) -> GroupNodeBlob:
        """
        The stock blob a creation preset selects (used when no explicit pipeline is posted).

        An unknown or omitted preset falls back to the default (``standard``), mirroring the lenient
        selection the create endpoint has always had.

        Args:
            preset (str | None): The preset name, or None for the default.

        Returns:
            GroupNodeBlob: The selected stock topology.
        """
        method_name = cls._PRESET_BLOBS.get(preset or "standard", "default_blob")
        return getattr(cls, method_name)()


__all__ = ["IngestPipeline"]
