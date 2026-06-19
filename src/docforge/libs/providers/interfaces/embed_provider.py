# ====== Code Summary ======
# EmbedProvider Protocol — defines the interface for embedding backends that produce dense
# (and optionally sparse) vectors for text chunks. BGE-M3 via TEI is the primary implementation.

# ====== Standard Library Imports ======
from __future__ import annotations

from typing import Protocol, runtime_checkable

# ====== Third-Party Library Imports ======
# (none — Protocol and result types only)
# ====== Internal Project Imports ======
from libs.capabilities.results import EmbedResult

# ====== Local Project Imports ======
# (none)


@runtime_checkable
class EmbedProvider(Protocol):
    """Produces dense (and optionally sparse) embedding vectors for text chunks."""

    name: str
    version: str
    runs_on: str
    dimension: int

    async def embed(self, texts: list[str]) -> EmbedResult:
        """
        Embed a batch of texts.

        Args:
            texts (list[str]): Input strings to embed.

        Returns:
            EmbedResult: One vector per input text.
        """
        ...
