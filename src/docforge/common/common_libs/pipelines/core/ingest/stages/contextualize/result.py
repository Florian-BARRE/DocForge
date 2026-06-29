# ====== Code Summary ======
# IngestStageContextualizeResult — the tally artefact of the contextualize stage (ported from the
# former S5Result). It carries the contextualized chunk list and how many chunks received a
# non-empty embed_text, so downstream tracing/reporting can surface the contextualization coverage.

# ====== Standard Library Imports ======
from dataclasses import dataclass

# ====== Internal Project Imports ======
from common_libs.domain import Chunk


@dataclass(slots=True)
class IngestStageContextualizeResult:
    """
    Output tally of the contextualize stage.

    Attributes:
        chunks (list[Chunk]): The chunks with ``embed_text`` populated.
        n_contextualized (int): Number of chunks that received a non-empty ``embed_text``.
    """

    chunks: list[Chunk]
    n_contextualized: int


__all__ = ["IngestStageContextualizeResult"]
