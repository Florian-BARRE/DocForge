# ====== Code Summary ======
# S5Result dataclass — output of the S5 contextualization stage.
# Extracted from s5_contextualize.py to keep the result model separately importable
# without pulling in S5ContextualizeStage's dependencies.

# ====== Standard Library Imports ======
from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from libs.core.ir.chunk import Chunk


@dataclass(slots=True)
class S5Result:
    """
    Output of the S5 contextualization stage.

    Attributes:
        chunks (list[Chunk]): Chunks with embed_text populated.
        n_contextualized (int): Number of chunks that received a non-empty embed_text.
    """

    chunks: list[Chunk]
    n_contextualized: int
