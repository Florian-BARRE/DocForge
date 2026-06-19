# ====== Code Summary ======
# EmbedResult Pydantic model returned by EmbedProvider implementations.
# Carries dense vectors, optional sparse BM25 maps, and the model name.
# Embed success is binary — the quality score is always 1.0 for a successful call.

# ====== Standard Library Imports ======
from __future__ import annotations

# ====== Third-Party Library Imports ======
from pydantic import BaseModel

# ====== Internal Project Imports ======
# (none)

# ====== Local Project Imports ======
# (none)


class EmbedResult(BaseModel):
    """
    Output of a text embedding call (dense + optional sparse for hybrid search).

    Attributes:
        vectors (list[list[float]]): One dense vector per input text.
        sparse (list[dict[int, float]] | None): One BM25 sparse map per text
            mapping token_id → weight, or None if the provider does not support
            sparse embeddings.
        model (str): Name of the embedding model used.
        quality (float): Always 1.0 for a successful call — embeddings are binary
            success/fail; gate escalation flows via attempt.error instead.
    """

    vectors: list[list[float]]              # one dense vector per input text
    sparse: list[dict[int, float]] | None = None  # one BM25 sparse map per text (token_id → weight)
    model: str
    quality: float = 1.0  # embeddings are binary success/fail — gate escalation flows via attempt.error

    def score(self) -> float | None:
        """
        Return the escalation score for the chain gate.

        Returns:
            float | None: Always 1.0 — a successful embed call is considered perfect quality.
        """
        return self.quality
