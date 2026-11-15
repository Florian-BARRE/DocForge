# ====== Code Summary ======
# Device: the closed set of compute devices a model host reports on GET /health. The DocForge app's
# GET /capabilities probe reads the `device` field and checks `== "cuda"`, so the values are a
# cross-service contract: exactly "cuda" or "cpu".

# ====== Standard Library Imports ======
from __future__ import annotations

from enum import Enum


class Device(str, Enum):
    """Runtime compute device of a model host."""

    CUDA = "cuda"
    CPU = "cpu"
