# ====== Code Summary ======
# FakeCudaDetector: a CudaDetector double with a scripted answer (or failure) and a call counter.

# ====== Standard Library Imports ======
from __future__ import annotations

# ====== Internal Project Imports ======
from model_server_core import CudaDetector


class FakeCudaDetector(CudaDetector):
    """Answers `answer`, or raises RuntimeError when `fail` is set."""

    def __init__(self, answer: bool = False, *, fail: bool = False) -> None:
        self._answer = answer
        self._fail = fail
        self.calls = 0

    def is_cuda_available(self) -> bool:
        self.calls += 1
        if self._fail:
            raise RuntimeError("probe exploded")
        return self._answer
