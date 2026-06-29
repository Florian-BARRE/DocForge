# ====== Code Summary ======
# The frozen identity/policy descriptors a concrete node declares as its single SPEC ClassVar.
# NodeSpec carries what every node needs (key/name/description + error policy); StageSpec extends it
# with the stage-only caching contract (cache policy + code version fed to the node fingerprint).
# Serialisable Pydantic models (frozen): a node's contract lives in a single source of truth that the
# engine, the resolver, and describe() all read, and that the API can emit as-is.

# ====== Third-Party Library Imports ======
from pydantic import BaseModel, ConfigDict, Field

# ====== Local Project Imports ======
from .enums import CachePolicy, ErrorPolicy


class NodeSpec(BaseModel):
    """
    Frozen identity + error contract every node declares as its single ``SPEC`` ClassVar.

    Attributes:
        key (str): Stable node identifier (unique among its siblings). For stages this is a
            ``StageKey`` value (a ``str`` at runtime).
        name (str): Human-readable node name.
        description (str): One-line description of what the node does.
        error_policy (ErrorPolicy): What the engine does when this node fails. Authoritative.
    """

    model_config = ConfigDict(frozen=True)

    key: str = Field(description="Stable node identifier, unique among siblings.")
    name: str = Field(description="Human-readable node name.")
    description: str = Field(default="", description="One-line description of the node.")
    error_policy: ErrorPolicy = Field(
        default=ErrorPolicy.FAIL, description="Authoritative error policy."
    )


class StageSpec(NodeSpec):
    """
    Stage-level descriptor — a ``NodeSpec`` plus the caching contract used by the engine middleware.

    Attributes:
        cache_policy (CachePolicy): How the stage is cached by the engine.
        code_version (str): Stage code version fed as ``code_version`` to the node fingerprint;
            bump it to invalidate the node cache for this stage.
    """

    cache_policy: CachePolicy = Field(
        default=CachePolicy.IDEMPOTENT_WRITE, description="Stage caching strategy."
    )
    code_version: str = Field(default="1.0", description="Stage code version (cache-busting).")


__all__ = ["NodeSpec", "StageSpec"]
