# ====== Code Summary ======
# Abstract base class for all embedding providers.
# Every embed provider must inherit EmbedProvider and implement dimension + embed.

# ====== Standard Library Imports ======
from __future__ import annotations

from abc import ABC, abstractmethod

# ====== Internal Project Imports ======
from providers.interfaces import EmbedResult


class EmbedProvider(ABC):
    """
    Abstract base class for all embedding providers.

    Subclasses implement one embedding protocol (TEI, OpenAI-compat, etc.) and
    are instantiated by ``StageEngine._build_s6_from_config`` based on the
    collection's ``embed.provider.id``.

    Class attributes:
        name (str): Provider identifier used in logs and fingerprints.
        version (str): Default model name — used in cache keys when ``model`` is omitted.
        runs_on (str): Deployment location — ``"local"`` or ``"remote"``.
    """

    name: str
    version: str
    runs_on: str

    @property
    @abstractmethod
    def dimension(self) -> int:
        """
        Dense vector dimension produced by this provider.

        Used by S6 to configure the Qdrant collection with the correct vector size.

        Returns:
            int: Number of floats in each dense embedding vector.
        """
        ...

    @abstractmethod
    async def embed(self, texts: list[str]) -> EmbedResult:
        """
        Embed a list of texts and return dense (and optionally sparse) vectors.

        Args:
            texts (list[str]): Input strings to embed.  May be empty.

        Returns:
            EmbedResult: One dense vector per input text; sparse maps when supported.
        """
        ...
