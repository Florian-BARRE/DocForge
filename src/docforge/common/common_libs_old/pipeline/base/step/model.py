# ====== Code Summary ======
# StepSchema — the self-describing shape emitted by a step's describe(). It is the leaf of the
# recursive pipeline -> stage -> step describe tree consumed by /discovery (and, later, the UI).
# A plain step emits identity + typed IO; a ChainStep additionally emits its provider category
# and the ordered provider choices in its chain. Pure Pydantic model: no behaviour.

# ====== Standard Library Imports ======
from __future__ import annotations

# ====== Third-Party Library Imports ======
from pydantic import BaseModel, Field


class StepSchema(BaseModel):
    """
    Self-description of a single step.

    Attributes:
        kind (str): ``"step"`` for a plain step, ``"chain"`` for a ``ChainStep``.
        key (str): Stable step identifier (unique within its stage).
        name (str): Human-readable step name.
        description (str): One-line description of what the step does.
        consumes (list[str]): Context keys the step reads.
        produces (list[str]): Context keys the step writes.
        category (str | None): Provider category (chain steps only; e.g. ``"ocr"``).
        providers (list[str]): Ordered provider ids in the chain (chain steps only).
    """

    kind: str = Field(description="Step kind: 'step' or 'chain'.")
    key: str = Field(description="Stable step identifier, unique within its stage.")
    name: str = Field(description="Human-readable step name.")
    description: str = Field(default="", description="One-line description of the step.")
    consumes: list[str] = Field(default_factory=list, description="Context keys read.")
    produces: list[str] = Field(default_factory=list, description="Context keys written.")
    category: str | None = Field(
        default=None, description="Provider category (chain steps only)."
    )
    providers: list[str] = Field(
        default_factory=list, description="Ordered provider ids (chain steps only)."
    )


__all__ = ["StepSchema"]
