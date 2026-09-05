# ====== Code Summary ======
# The catalogue of available building blocks — the palette the UI offers to assemble a pipeline.
# It walks the NodeRegistry and, per family, lists every registered node's type card (its
# describe()), so the frontend can render "which providers exist and how each is configured" with
# zero hardcoded text. Instance-free: it describes TYPES, not a built pipeline (that is the
# explorer's job).

# ====== Third-Party Library Imports ======
from pydantic import BaseModel

# ====== Internal Project Imports ======
from shared_libs.pipelines.base import IoSlot, NodeDescription
from shared_libs.pipelines.registry import FamilyMode, NodeRegistry

# ====== Local Project Imports ======
from .artefacts import ArtefactCard
from .mechanics import MechanicsDescription


class FamilyCatalog(BaseModel):
    """
    The registered nodes of a single family, with the family's usage semantics.

    Attributes:
        family (str): Capability family (e.g. ``"llm"``).
        title (str): Human label (falls back to the key when the family declared none).
        description (str): What the family does and how its nodes combine.
        mode (FamilyMode): How the nodes are meant to be used together (exclusive / stackable /
            chain / stage) — the UI adapts its editor to it.
        nodes (list[NodeDescription]): The type card of every node registered in that family.
    """

    family: str
    title: str = ""
    description: str = ""
    mode: FamilyMode = FamilyMode.STAGE
    nodes: list[NodeDescription]

    @classmethod
    def from_family(cls, family: str, kinds: set[str] | None = None) -> "FamilyCatalog":
        """
        Build one family's catalogue: its declared metadata + its node cards.

        Args:
            family (str): Capability family to describe.
            kinds (set[str] | None): Optional allowlist. When given, only node cards whose
                kind is in the set are kept — used to scope a SHARED family (e.g. ``deliver``)
                to the kinds that belong to the requesting pipeline kind. When ``None``, every
                registered node card of the family is listed (the default).

        Returns:
            FamilyCatalog: The family's metadata and its (optionally filtered) node cards.
        """
        info = NodeRegistry.family_info(family)
        nodes = NodeRegistry.catalog(family)
        if kinds is not None:
            nodes = [node for node in nodes if node.kind in kinds]
        return cls(
            family=family,
            title=info.title if info else family,
            description=info.description if info else "",
            mode=info.mode if info else FamilyMode.STAGE,
            nodes=nodes,
        )


class Palette(BaseModel):
    """
    The catalogue of building blocks, grouped by family.

    The DEFAULT palette carries only ``families`` — everything the product stage rail needs.
    The three advanced blocks below are ``None`` unless the FULL palette is requested (the
    graph-level design surface: ``GET …?full=true``), so the common payload never pays the
    cost of describing mechanics and artefacts it will not render.

    Attributes:
        families (list[FamilyCatalog]): One entry per registered family.
        run_inputs (list[IoSlot] | None): The artefacts the RUN provides to the graph — what a
            ``FromRunInput`` binding can target. Advanced only: wiring the entry contract is a
            graph-editing concern.
        mechanics (MechanicsDescription | None): The graph-structure vocabulary (conditions,
            binding sources, containers, error policies) — auto-derived from the base models.
            Advanced only: it feeds edge/loop editors.
        artefacts (dict[str, ArtefactCard] | None): The slot-type vocabulary — every artefact
            model's docstring + JSON Schema, keyed by class name. Advanced only: it feeds the
            type-chip inspector.
    """

    families: list[FamilyCatalog]
    run_inputs: list[IoSlot] | None = None
    mechanics: MechanicsDescription | None = None
    artefacts: dict[str, ArtefactCard] | None = None


__all__ = ["FamilyCatalog", "Palette"]
