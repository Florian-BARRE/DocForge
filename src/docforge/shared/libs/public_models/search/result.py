# ====== Code Summary ======
# SearchResult — the TERMINAL output contract of the search pipeline (the search analog of the
# ingestion RunBundle). The app-side runner asserts the graph's final output is exactly this
# artefact before returning it to the caller: the original query, the ranked hits, and an optional
# debug bag (timings, filter notes, escalation trace).

# ====== Third-Party Library Imports ======
from pydantic import Field

# ====== Internal Project Imports ======
from ..base import Artifact
from .elements import Hit


class SearchResult(Artifact):
    """
    The search pipeline's terminal output — the ranked answer to one query.

    Attributes:
        query (str): The original query text the run answered.
        hits (list[Hit]): The ranked hits (rank 1 first) delivered to the caller.
        debug (dict | None): Optional trace bag — timings, dropped filters, escalation notes;
            None in the lean path.
    """

    query: str = Field(description="The original query text the run answered.")
    hits: list[Hit] = Field(default_factory=list, description="The ranked hits (rank 1 first).")
    debug: dict | None = Field(
        default=None, description="Optional trace bag (timings, filter notes, escalation trace)."
    )


__all__ = ["SearchResult"]
