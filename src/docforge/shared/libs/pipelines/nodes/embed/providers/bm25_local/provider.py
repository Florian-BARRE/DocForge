# ====== Code Summary ======
# The bm25_local sparse provider — an explicit, selectable, in-process BM25 encoder (Snowball FR+EN
# analysis, hashed term ids, saturated TF). No network, no model. Its vectors are term frequencies,
# so the collection's sparse vectors (content_bm25 AND every meta_*_bm25) must be declared with the
# Qdrant IDF modifier — SPARSE_IDF=True is what the vector schema derives that from. The document
# side normalises length against a role-specific reference (a chunk body vs a short metadata value);
# the query side is the unique-term vector.

# ====== Standard Library Imports ======
from typing import Literal

# ====== Third-Party Library Imports ======
from pydantic import Field

# ====== Internal Project Imports ======
from shared_libs.public_models import SparseVector

# ====== Local Project Imports ======
from ..base import EmbedAxis, EmbedProvider, EmbedProviderConfig, EmbedRole
from ..registry import EmbedProviderRegistry
from .encoder import Bm25Encoder


class Bm25LocalProviderConfig(EmbedProviderConfig):
    """The local BM25 encoder's knobs (no endpoint — it runs in-process)."""

    kind: Literal["bm25_local"] = Field(default="bm25_local", description="Provider kind.")
    model: str = Field(
        default=Bm25Encoder.ENCODING,
        description="Encoding identity (provenance) — the analysis + hash version.",
    )
    k1: float = Field(default=1.2, gt=0, description="BM25 term-frequency saturation.")
    b: float = Field(default=0.75, ge=0, le=1, description="BM25 length normalisation strength.")
    content_reference_length: float = Field(
        default=256.0,
        gt=0,
        description="Reference length (tokens) a chunk body is normalised against (a per-text "
        "encoder cannot know the corpus average).",
    )
    field_reference_length: float = Field(
        default=8.0,
        gt=0,
        description="Reference length (tokens) a metadata value is normalised against (values are "
        "short names/titles).",
    )


@EmbedProviderRegistry.register
class Bm25LocalProvider(EmbedProvider):
    """Sparse BM25 vectors computed in-process; Qdrant supplies the IDF."""

    KIND = "bm25_local"
    AXES = frozenset({EmbedAxis.SPARSE})
    SPARSE_IDF = True
    Config = Bm25LocalProviderConfig

    async def embed_sparse(
        self, texts: list[str], role: EmbedRole = EmbedRole.CONTENT
    ) -> list[SparseVector]:
        """BM25 term-frequency vectors, length-normalised against the role's reference length."""
        config: Bm25LocalProviderConfig = self.config  # type: ignore[assignment]
        reference = (
            config.content_reference_length
            if role == EmbedRole.CONTENT
            else config.field_reference_length
        )
        return [
            Bm25Encoder.encode_document(text, k1=config.k1, b=config.b, reference_length=reference)
            for text in texts
        ]

    async def embed_query_sparse(self, text: str) -> SparseVector:
        """The query's unique-term vector (weight 1 — the IDF comes from Qdrant)."""
        return Bm25Encoder.encode_query(text)


__all__ = ["Bm25LocalProvider", "Bm25LocalProviderConfig"]
