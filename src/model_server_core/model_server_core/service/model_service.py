# ====== Code Summary ======
# ModelService: the contract of what a model server hosts (the loaded model, or an aggregate of
# several pipelines). The ModelServer only needs to know whether it is ready, to load it at startup
# and to unload it at shutdown; everything model-specific (predict, locks, batching) stays in the
# server's own subclass.

# ====== Standard Library Imports ======
from __future__ import annotations

from abc import ABC, abstractmethod


class ModelService(ABC):
    """Contract between a `ModelServer` and the model it hosts."""

    @property
    @abstractmethod
    def ready(self) -> bool:
        """True once every pipeline the server needs is built and able to serve."""

    def load(self) -> None:
        """Build the model(s). Called once at startup, after config validation.

        The default is a no-op, for a service that loads lazily on its first request.
        """

    def unload(self) -> None:
        """Release the model(s). Called once at shutdown, even after a partial startup.

        Implementations MUST be a safe no-op when nothing (or only part of the model) was loaded.
        """
