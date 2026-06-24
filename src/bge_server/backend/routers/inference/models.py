# ====== Code Summary ======
# Pydantic request and response models for POST /embed, POST /embed_sparse, and POST /rerank.
# All shapes are frozen to the TEI contract so the DocForge `tei` embed provider and
# `bge_reranker` rerank provider can drive this service without any provider-side changes.

# ====== Third-Party Library Imports ======
from pydantic import BaseModel, Field


# ── Request models ────────────────────────────────────────────────────────────

class EmbedRequest(BaseModel):
    """
    TEI-compatible request body for POST /embed and POST /embed_sparse.

    Attributes:
        inputs (list[str] | str): One text or a list of texts to embed.
        normalize (bool): L2-normalize dense vectors (kept for TEI parity; FlagEmbedding
            always normalizes dense output, so this flag is accepted but not forwarded).
        truncate (bool): Truncate inputs to the model's max token length.
    """

    inputs: list[str] | str = Field(..., description="One text or a list of texts to embed.")
    normalize: bool = Field(default=True, description="L2-normalize dense vectors (TEI parity).")
    truncate: bool = Field(default=True, description="Truncate inputs to the model max length.")


class RerankRequest(BaseModel):
    """
    TEI-compatible request body for POST /rerank.

    Attributes:
        query (str): The search query to score candidates against.
        texts (list[str]): Candidate texts to score.
        truncate (bool): Truncate inputs to the model's max token length.
    """

    query: str = Field(..., description="The search query.")
    texts: list[str] = Field(..., description="Candidate texts to score against the query.")
    truncate: bool = Field(default=True, description="Truncate inputs to the model max length.")


# ── Response models ───────────────────────────────────────────────────────────

class SparseToken(BaseModel):
    """
    A single token in a TEI sparse embedding response.

    Attributes:
        index (int): Token ID in the model vocabulary.
        value (float): Lexical weight assigned to this token.
    """

    index: int = Field(..., description="Token ID in the model vocabulary.")
    value: float = Field(..., description="Lexical weight for this token.")


class RerankResult(BaseModel):
    """
    A single scored candidate in the POST /rerank response.

    Attributes:
        index (int): Position of this candidate in the original ``texts`` list.
        score (float): Sigmoid-normalized cross-encoder score in [0, 1].
    """

    index: int = Field(..., description="Position of this candidate in the input texts list.")
    score: float = Field(..., description="Sigmoid-normalized reranking score in [0, 1].")
