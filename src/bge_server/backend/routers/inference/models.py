# ====== Code Summary ======
# Pydantic request and response models for POST /embed, POST /embed_sparse, POST /embed_colbert,
# and POST /rerank. The /embed, /embed_sparse, and /rerank shapes are frozen to the TEI contract
# so the DocForge `tei` embed provider and `bge_reranker` rerank provider can drive this service
# without any provider-side changes. /embed_colbert is an internal DocForge convention (BGE-M3
# native colbert head, no TEI equivalent) — its response shape has no wrapper model, mirroring
# how /embed itself returns a bare `list[list[float]]` with no pydantic model.
#
# Request size ceilings (BGE_MAX_REQUEST_ITEMS / BGE_MAX_TEXT_CHARS) reject oversized requests
# here, at the Pydantic layer (HTTP 422), before they ever reach the batching engine — see
# config_loader.py for the rationale (an oversized request is admitted "whole" by
# BatchQueueWorker and holds the shared model lock for its entire duration).

# ====== Third-Party Library Imports ======
from pydantic import BaseModel, Field, field_validator

# ====== Internal Project Imports ======
from config_loader import BgeServerConfig

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

    @field_validator("inputs")
    @classmethod
    def _enforce_size_ceilings(cls, value: list[str] | str) -> list[str] | str:
        """
        Reject requests exceeding the configured item-count / per-item char ceilings.

        Args:
            value (list[str] | str): The raw ``inputs`` value (single text or a list).

        Returns:
            list[str] | str: The value unchanged, when within both ceilings.

        Raises:
            ValueError: When the item count or any individual text exceeds its ceiling
                (surfaced by FastAPI as HTTP 422).
        """
        items = [value] if isinstance(value, str) else value
        if len(items) > BgeServerConfig.BGE_MAX_REQUEST_ITEMS:
            raise ValueError(
                f"inputs has {len(items)} items, exceeds the "
                f"{BgeServerConfig.BGE_MAX_REQUEST_ITEMS}-item request ceiling"
            )
        for text in items:
            if len(text) > BgeServerConfig.BGE_MAX_TEXT_CHARS:
                raise ValueError(
                    f"an input text has {len(text)} chars, exceeds the "
                    f"{BgeServerConfig.BGE_MAX_TEXT_CHARS}-char per-item ceiling"
                )
        return value


class RerankRequest(BaseModel):
    """
    TEI-compatible request body for POST /rerank.

    Attributes:
        query (str): The search query to score candidates against.
        texts (list[str]): Candidate texts to score.
        truncate (bool): Truncate inputs to the model's max token length.
    """

    query: str = Field(
        ...,
        description="The search query.",
        max_length=BgeServerConfig.BGE_MAX_TEXT_CHARS,
    )
    texts: list[str] = Field(
        ...,
        description="Candidate texts to score against the query.",
        max_length=BgeServerConfig.BGE_MAX_REQUEST_ITEMS,
    )
    truncate: bool = Field(default=True, description="Truncate inputs to the model max length.")

    @field_validator("texts")
    @classmethod
    def _enforce_text_char_ceiling(cls, value: list[str]) -> list[str]:
        """
        Reject any candidate text exceeding the per-item char ceiling.

        The item-count ceiling itself is already enforced by the ``max_length`` Field
        constraint above (unambiguous here since ``texts`` — unlike ``EmbedRequest.inputs``
        — has no ``str`` union branch).

        Args:
            value (list[str]): Candidate texts to score.

        Returns:
            list[str]: The value unchanged, when every text is within the ceiling.

        Raises:
            ValueError: When a candidate text exceeds the char ceiling (HTTP 422).
        """
        for text in value:
            if len(text) > BgeServerConfig.BGE_MAX_TEXT_CHARS:
                raise ValueError(
                    f"a candidate text has {len(text)} chars, exceeds the "
                    f"{BgeServerConfig.BGE_MAX_TEXT_CHARS}-char per-item ceiling"
                )
        return value


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


# Per input text, a list of per-token 1024-dim L2-normalized float vectors (variable length
# per text). Documents the POST /embed_colbert response shape — not a pydantic model, mirroring
# the un-wrapped `list[list[float]]` response of POST /embed.
ColbertTokenVectors = list[list[list[float]]]
