# ====== Code Summary ======
# PipelineSchema — the root of the self-describing describe tree. A pipeline's describe()
# returns this; it recurses into StageSchema -> StepSchema, so /discovery can render the whole
# pipeline (stages, steps, chains, provider choices) with zero hardcoded text. Pure Pydantic.

# ====== Standard Library Imports ======
from __future__ import annotations

# ====== Third-Party Library Imports ======
from pydantic import BaseModel, Field

# ====== Internal Project Imports ======
from common_libs.pipeline.base.stage.model import StageSchema


class PipelineSchema(BaseModel):
    """
    Self-description of a whole pipeline — the root of the recursive describe tree.

    Attributes:
        key (str): Stable pipeline identifier (e.g. ``"ingest"``, ``"search"``).
        name (str): Human-readable pipeline name.
        description (str): One-line description of the pipeline.
        stages (list[StageSchema]): Stage schemas in topological (execution) order.
    """

    key: str = Field(description="Stable pipeline identifier.")
    name: str = Field(description="Human-readable pipeline name.")
    description: str = Field(default="", description="One-line description of the pipeline.")
    stages: list[StageSchema] = Field(
        default_factory=list, description="Stage schemas in topological order."
    )


__all__ = ["PipelineSchema"]
