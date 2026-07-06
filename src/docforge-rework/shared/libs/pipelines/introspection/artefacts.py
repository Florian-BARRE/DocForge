# ====== Code Summary ======
# Self-description of the ARTEFACT vocabulary — the shared BaseModels that flow between nodes
# (SourceDocument, IntakeResult, DocumentIR, Chunk…). Collected automatically from every
# registered node's Consumes/Produces faces, each exposed with its docstring and its full JSON
# Schema, so the UI can open any slot type and show the model's fields with their descriptions —
# zero hardcoded knowledge, one more application of the describe pattern.

# ====== Standard Library Imports ======
import inspect
from typing import Any

# ====== Third-Party Library Imports ======
from pydantic import BaseModel, Field

# ====== Local Project Imports ======
from ..base import ActionNode, SlotTypes
from ..registry import NodeRegistry


class ArtefactCard(BaseModel):
    """
    UI-facing description of one artefact model (a slot type).

    Attributes:
        name (str): The model's class name — the token IoSlot.artefact_type refers to.
        summary (str): One-line statement from the model's docstring.
        json_schema (dict): The model's full JSON Schema (fields, types, descriptions, $defs) —
            what the UI renders when the user opens a type chip.
    """

    name: str
    summary: str
    json_schema: dict[str, Any] = Field(default_factory=dict)


class ArtefactCatalog:
    """Static builder of the artefact vocabulary from every registered node's typed faces."""

    def __new__(cls, *args: object, **kwargs: object) -> None:
        raise TypeError("ArtefactCatalog is a static-only class and cannot be instantiated.")

    @classmethod
    def describe(cls) -> dict[str, ArtefactCard]:
        """
        Collect every artefact class reachable through a registered node's slots.

        Returns:
            dict[str, ArtefactCard]: One card per artefact model, keyed by class name (the
            same token the palette's IoSlot.artefact_type carries, list[...] unwrapped).
        """
        # 1. Walk the registry: every Consumes/Produces slot names an artefact class.
        models: dict[str, type[BaseModel]] = {}
        for family in NodeRegistry.families():
            for kind in NodeRegistry.kinds(family):
                node_class = NodeRegistry.get(family, kind)
                if not (isinstance(node_class, type) and issubclass(node_class, ActionNode)):
                    continue
                for face_name in ("Consumes", "Produces"):
                    face: type[BaseModel] = getattr(node_class, face_name)
                    for field_info in face.model_fields.values():
                        element, _is_list = SlotTypes.element(field_info.annotation)
                        if element is not None and issubclass(element, BaseModel):
                            models[element.__name__] = element

        # 2. One card per model: docstring first line + full JSON Schema.
        cards: dict[str, ArtefactCard] = {}
        for name, model in sorted(models.items()):
            doc = inspect.cleandoc(model.__doc__ or "")
            summary = doc.split("\n\n", 1)[0].replace("\n", " ").strip()
            cards[name] = ArtefactCard(name=name, summary=summary, json_schema=model.model_json_schema())
        return cards


__all__ = ["ArtefactCard", "ArtefactCatalog"]
