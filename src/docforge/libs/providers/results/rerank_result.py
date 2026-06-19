# ====== Code Summary ======
# RerankResult Pydantic model returned by RerankProvider implementations.
# Carries a relevance score per input document, preserving the original input order.

# ====== Standard Library Imports ======
# (none)

# ====== Third-Party Library Imports ======
from pydantic import BaseModel

# ====== Internal Project Imports ======
# (none)

# ====== Local Project Imports ======
# (none)


class RerankResult(BaseModel):
    """
    Output of a reranking call.

    Attributes:
        scores (list[float]): Relevance score per input document, in the same
            order as the input list passed to the provider.
    """

    scores: list[float]  # relevance score per input document, same order as input
