# ====== Code Summary ======
# SearchTarget — the caller's per-field choice of WHAT to search: a field (the chunk "content" or a
# metadata field name) and which of its indexed vectors to query (semantic = the dense vector,
# lexical = the sparse BM25 vector). A query carries a LIST of targets, so it can search content,
# a metadata field, several fields, or metadata ONLY — each on its own modality. It is a plain value
# object carried inside RawQuery/QuerySpec; the target → named-vector translation lives ONLY in the
# app read port (it is the single place that knows Qdrant vector names).

# ====== Third-Party Library Imports ======
from pydantic import BaseModel, ConfigDict, Field

# The sentinel field name standing for the chunk body (not a metadata field) — the port maps it to
# the content_dense / content_bm25 vectors; any other value is a metadata field name.
CONTENT_FIELD = "content"


class SearchTarget(BaseModel):
    """
    One field to search and the modalities to search it on.

    A target names a field — the literal ``"content"`` (the chunk body) or a metadata field name —
    and turns on the vectors to query it with: ``semantic`` queries the field's dense vector,
    ``lexical`` its sparse BM25 vector. A target with neither modality selects nothing and is a
    caller error the API rejects.

    Attributes:
        field (str): The field to search — ``"content"`` for the chunk body, else a metadata field
            name (matched against the collection's schema, resolved to ``meta_<slug>_*`` vectors).
        semantic (bool): Query the field's dense vector (semantic similarity).
        lexical (bool): Query the field's sparse BM25 vector (lexical match).
    """

    model_config = ConfigDict(extra="forbid")

    field: str = Field(
        default=CONTENT_FIELD,
        description="Field to search — 'content' (chunk body) or a metadata field name.",
    )
    semantic: bool = Field(
        default=False, description="Query the field's dense vector (semantic similarity)."
    )
    lexical: bool = Field(
        default=False, description="Query the field's sparse BM25 vector (lexical match)."
    )


def default_content_targets() -> list[SearchTarget]:
    """
    Build the default target list — content on both modalities (today's plain-query behaviour).

    Returns:
        list[SearchTarget]: A single content target with semantic AND lexical on, so an untouched
        query searches content exactly as it did before search targets existed.
    """
    # 1. One content target, both axes on — byte-identical to the pre-targets default path.
    return [SearchTarget(field=CONTENT_FIELD, semantic=True, lexical=True)]


__all__ = ["SearchTarget", "CONTENT_FIELD", "default_content_targets"]
