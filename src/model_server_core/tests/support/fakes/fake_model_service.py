# ====== Code Summary ======
# FakeModelService: an in-memory ModelService double that records its lifecycle calls and can be made
# to fail on load, for the lifespan and health tests.

# ====== Standard Library Imports ======
from __future__ import annotations

# ====== Internal Project Imports ======
from model_server_core import ModelService


class FakeModelService(ModelService):
    """A ModelService whose readiness and failures are scripted.

    Args:
        ready_after_load (bool): Whether `ready` turns True once `load()` ran.
        fail_on_load (bool): Make `load()` raise RuntimeError.
    """

    def __init__(self, *, ready_after_load: bool = True, fail_on_load: bool = False) -> None:
        self.calls: list[str] = []
        self._ready = False
        self._ready_after_load = ready_after_load
        self._fail_on_load = fail_on_load

    @property
    def ready(self) -> bool:
        return self._ready

    def load(self) -> None:
        self.calls.append("load")
        if self._fail_on_load:
            raise RuntimeError("load failed")
        self._ready = self._ready_after_load

    def unload(self) -> None:
        self.calls.append("unload")
        self._ready = False
