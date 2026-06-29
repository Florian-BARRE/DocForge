# ====== Code Summary ======
# The capability contract — the marker every reusable material (a provider, a chain, an app service
# handle) conforms to so it can be placed in the hierarchical CapabilityRegistry and resolved by a
# node's REQUIRES. The base layer of the fractal capabilities cascade: it holds only the contract;
# concrete families (parser/ocr/vlm/embed/rerank/llm + the escalation chain) live in sibling
# packages and specialise downward into the pipeline tree.

# ====== Standard Library Imports ======
from typing import Protocol, runtime_checkable


@runtime_checkable
class Capability(Protocol):
    """
    Structural contract for a reusable material resolvable through the capability registry.

    A capability is anything a node may require to do its work — an app-service handle (s3, Postgres,
    Qdrant), a provider, or a provider-escalation chain. It exposes a stable ``name`` used as its
    registry key, so a node's ``CapabilityRef(name)`` resolves to it up the ancestor chain.

    Attributes:
        name (str): Stable registry key for this capability.
    """

    @property
    def name(self) -> str:
        """Stable registry key for this capability."""
        ...


__all__ = ["Capability"]
