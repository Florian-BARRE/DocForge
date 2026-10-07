# ====== Code Summary ======
# TermlessQueryHint — the honest explanation when a metadata lexical target could not be queried
# because the query carries no searchable BM25 term (stopwords/punctuation only). Without it the empty
# answer reads as "nothing matched", when in fact no lexical query was ever sent. Pure: it reads the
# per-request retrieval probe's record, filled by the read port only on that exact cause.

# ====== Local Project Imports ======
from .filter_hint import FilterHint
from .probe import SearchRetrievalProbe


class TermlessQueryHint:
    """Static builder of the "query has no searchable term for this lexical target" hints."""

    def __new__(cls, *args: object, **kwargs: object) -> None:
        raise TypeError("TermlessQueryHint is a static-only class and cannot be instantiated.")

    @staticmethod
    def build(probe: SearchRetrievalProbe, query: str) -> list[FilterHint]:
        """
        Return one hint per metadata lexical target the query had no BM25 term for.

        Args:
            probe (SearchRetrievalProbe): The request's retrieval probe.
            query (str): The query as the caller sent it.

        Returns:
            list[FilterHint]: One hint per dropped target, empty when none was dropped for that cause.
        """
        # 1. One hint per target the read port recorded as termless.
        return [
            FilterHint(
                field=name,
                value=query,
                message=(
                    f"The query has no searchable term for lexical target '{name}' (only stopwords "
                    f"or punctuation), so nothing was searched — add a content word or use semantic."
                ),
            )
            for name in probe.termless_lexical_fields
        ]


__all__ = ["TermlessQueryHint"]
