# ====== Code Summary ======
# IngestPipeline — the class that TIES the ingestion pipeline together: it declares which node
# families compose it (its dedicated nodes + the generic capability families it uses), triggers
# their registration, and is the origin of the DESCRIBE the UI is populated from (the palette of
# every block available to assemble an ingestion pipeline). It will also carry the default
# topology as the stages are completed.

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
)
from shared_libs.pipelines.registry import NodeRegistry
from shared_libs.pipelines.validation import PaletteScopeValidator

# ====== Local Project Imports ======
from .stages import IngestAssembler, default_state, light_state


class IngestPipeline:
    """Static entry point of the ingestion pipeline — its families, its palette, its topology."""

    # The families an ingestion pipeline is assembled from: its DEDICATED nodes first, then the
    # GENERIC capability families its enrichment relies on.
    FAMILIES = (
        "intake",
        "converter",
        "parser",
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
            mechanics=GraphMechanics.describe(),
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


__all__ = ["IngestPipeline"]
