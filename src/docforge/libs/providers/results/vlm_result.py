# ====== Code Summary ======
# VlmResult Pydantic model returned by VlmProvider implementations.
# Carries the description, optional structured output, and a heuristic quality score
# used by the chain escalation gate.

# ====== Standard Library Imports ======
from __future__ import annotations

from typing import Any

# ====== Third-Party Library Imports ======
from pydantic import BaseModel

# ====== Internal Project Imports ======
# (none)

# ====== Local Project Imports ======
# (none)


class VlmResult(BaseModel):
    """
    Output of a VLM description call.

    The ``quality`` field encodes the in-adapter heuristic used by the chain gate:
      - ``1.0`` — structured output was requested and is present + non-empty.
      - ``0.5`` — only a description was returned (no schema / partial structured output).
      - ``0.0`` — the provider raised (the chain wrapper captures this case before
        the result is constructed; ``0.0`` is reserved as a sentinel).

    See ``providers/vlm/base.py`` for the helper that computes the value.

    Attributes:
        description (str): Natural-language description produced by the VLM.
        structured (dict[str, Any] | None): Optional structured data extracted
            by the VLM when a JSON schema was requested.
        quality (float): Heuristic quality estimate in [0.0, 1.0]. Defaults to 0.5.
    """

    description: str
    structured: dict[str, Any] | None = None
    quality: float = 0.5

    def score(self) -> float | None:
        """
        Return the escalation score for the chain gate.

        Returns:
            float | None: Heuristic quality estimate populated by the adapter.
        """
        return self.quality
