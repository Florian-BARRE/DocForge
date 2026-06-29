# ====== Code Summary ======
# Stage-level declarative enums + the self-describing StageSchema.
#   - ErrorPolicy: the stage's declarative ON_ERROR contract read by AbstractPipeline.run on a
#     stage exception (FAIL_DOC propagates fail-closed; SKIP/DEGRADE continue the run).
#   - CachePolicy: how the pipeline middleware caches the stage (NODE_CACHED = Merkle node cache,
#     today's S0/S1/S2; IDEMPOTENT_WRITE = PG/Qdrant ON CONFLICT idempotency, today's S4/S5/S5b/S6).
#   - StageSchema: the middle node of the describe tree, recursing into StepSchema leaves.

# ====== Standard Library Imports ======
from __future__ import annotations

from enum import StrEnum

# ====== Third-Party Library Imports ======
from pydantic import BaseModel, Field

# ====== Internal Project Imports ======
from common_libs.pipeline.base.step.model import StepSchema


class ErrorPolicy(StrEnum):
    """
    Declarative stage error policy — read by the pipeline engine on a stage exception.

    Members:
        FAIL_DOC: Fail-closed — propagate so the doc is marked failed (today's behaviour).
        SKIP: Skip the stage and continue the run (the stage produced nothing).
        DEGRADE: Continue the run in a degraded state (the stage produced partial output).
    """

    FAIL_DOC = "fail_doc"
    SKIP = "skip"
    DEGRADE = "degrade"


class CachePolicy(StrEnum):
    """
    Declarative stage cache policy — read by the pipeline caching middleware.

    Members:
        NODE_CACHED: Cached in the Merkle-DAG node cache (today's S0/S1/S2).
        IDEMPOTENT_WRITE: Not node-cached; idempotency comes from Postgres/Qdrant upserts
            (today's S4/S5/S5b/S6).
    """

    NODE_CACHED = "node_cached"
    IDEMPOTENT_WRITE = "idempotent_write"


class StageSchema(BaseModel):
    """
    Self-description of a single stage — recurses into its steps.

    Attributes:
        key (str): Stable stage identifier (unique within the pipeline).
        name (str): Human-readable stage name.
        description (str): One-line description of what the stage does.
        after (list[str]): Keys of the stages this stage must run after (the DAG edges).
        consumes (list[str]): Context keys the stage reads.
        produces (list[str]): Context keys the stage writes.
        cache_policy (CachePolicy): How the stage is cached by the pipeline middleware.
        on_error (ErrorPolicy): What the pipeline does when the stage raises.
        config (str | None): Name of the stage's Pydantic config model, when it declares one.
        steps (list[StepSchema]): One schema per step, in execution order.
    """

    key: str = Field(description="Stable stage identifier, unique within the pipeline.")
    name: str = Field(description="Human-readable stage name.")
    description: str = Field(default="", description="One-line description of the stage.")
    after: list[str] = Field(default_factory=list, description="Stage keys this runs after.")
    consumes: list[str] = Field(default_factory=list, description="Context keys read.")
    produces: list[str] = Field(default_factory=list, description="Context keys written.")
    cache_policy: CachePolicy = Field(description="Stage caching strategy.")
    on_error: ErrorPolicy = Field(description="Stage error policy.")
    config: str | None = Field(default=None, description="Stage config model name, if any.")
    steps: list[StepSchema] = Field(default_factory=list, description="Ordered step schemas.")


__all__ = ["ErrorPolicy", "CachePolicy", "StageSchema"]
