# ====== Code Summary ======
# The runtime carriers handed to a node when it executes. ServiceRegistry is the injected, live handles
# a node uses to work (S3 / Postgres / Qdrant / a converter…) — kept as a dataclass because it holds
# unserialisable connections. RunContext is the run-wide handle (the pipeline run input + the service
# registry). Context is what a node's ``execute`` receives: its already-resolved typed Input plus the
# services. One generic Context (no per-node subclass) keeps a node to a single file.

# ====== Standard Library Imports ======
from dataclasses import dataclass
from typing import Any

# ====== Local Project Imports ======
from .io import NodeInput


@dataclass(frozen=True, slots=True)
class ServiceRegistry:
    """The live, injected services a node may use, looked up by name."""

    items: dict[str, Any]

    def get(self, name: str) -> Any:
        """Return a service by name, or None when it is not registered."""
        return self.items.get(name)


@dataclass(frozen=True, slots=True)
class RunContext:
    """The run-wide handle: the pipeline run input (source of every FromRunInput) + the services."""

    run_input: NodeInput
    services: ServiceRegistry


@dataclass(slots=True)
class Context:
    """
    What a node's ``execute`` receives — its resolved typed input plus the live services.

    Attributes:
        input (NodeInput): The node's already-resolved typed Input (read its fields directly).
        services (ServiceRegistry): The injected live services (``ctx.service("object_store")``).
    """

    input: NodeInput
    services: ServiceRegistry

    def service(self, name: str) -> Any:
        """Look up an injected service by name."""
        return self.services.get(name)


__all__ = ["ServiceRegistry", "RunContext", "Context"]
