# ====== Code Summary ======
# HealthVerdictResolver — the pure roll-up of a collection's raw health signals (both graphs'
# buildability, the concatenated provider sweep, the vector count) into the two headline verdicts the
# UI drives its banner from: the overall ``verdict`` (operational / degraded / down) and the search
# ``search_operational`` tri-state (true / false / 'degraded'). It encodes ONE policy in one place —
# a critical provider (an embedder or any llm/vlm/ocr/converter the graph contains) being unreachable
# is a hard DOWN, a non-critical one (the reranker) or an empty index is only DEGRADED.

# ====== Third-Party Library Imports ======
from loggerplusplus import loggerplusplus

# ====== Internal Project Imports ======
from shared_libs.pipelines.reachability import ProbeStatus, ProviderProbeResult

# ====== Local Project Imports ======
from .models import HealthVerdict, SearchOperational

# Provider families whose reachability is load-bearing for the collection to function at all: the
# embedders (ingest + the search query embedder) and every paid text/vision/ocr/conversion provider
# the ingest graph actually contains. A down member here is a hard DOWN. The reranker is deliberately
# absent — search still returns (unranked-by-cross-encoder) results without it, so it is non-critical.
_CRITICAL_FAMILIES = frozenset({"embed", "llm", "vlm", "ocr", "converter"})

# The probe outcomes that mean a provider is unusable right now (a real reachability/credential
# failure). ``ok`` is healthy; ``skipped``/``not_configured`` mean there was nothing to reach.
_DOWN_STATUSES = frozenset({ProbeStatus.UNREACHABLE, ProbeStatus.AUTH_FAILED})


class HealthVerdictResolver:
    """Static roll-up of raw health signals into the overall + search verdicts."""

    logger = loggerplusplus.bind(identifier="HealthVerdictResolver")

    def __new__(cls, *args: object, **kwargs: object) -> None:
        raise TypeError("HealthVerdictResolver is a static-only class and cannot be instantiated.")

    @staticmethod
    def __is_down(probe: ProviderProbeResult) -> bool:
        """Whether a probe outcome means the provider is unusable now."""
        return probe.status in _DOWN_STATUSES

    @classmethod
    def __critical_down(cls, providers: list[ProviderProbeResult]) -> bool:
        """Whether any critical-family provider (embedder / llm / vlm / ocr / converter) is down."""
        return any(p.family in _CRITICAL_FAMILIES and cls.__is_down(p) for p in providers)

    @classmethod
    def __noncritical_down(cls, providers: list[ProviderProbeResult]) -> bool:
        """Whether any non-critical provider (e.g. the reranker) is down."""
        return any(p.family not in _CRITICAL_FAMILIES and cls.__is_down(p) for p in providers)

    @classmethod
    def overall(
        cls,
        *,
        ingest_buildable: bool,
        search_buildable: bool,
        providers: list[ProviderProbeResult],
        vector_count: int,
    ) -> HealthVerdict:
        """
        Roll the raw signals up into the overall operational verdict.

        Args:
            ingest_buildable (bool): Whether the ingest graph builds + validates.
            search_buildable (bool): Whether the search graph builds + validates.
            providers (list[ProviderProbeResult]): The concatenated ingest + search sweep.
            vector_count (int): The collection's indexed vector count.

        Returns:
            HealthVerdict: ``down`` when a blob is unbuildable or a critical provider is down;
            ``degraded`` when only a non-critical provider is down or the index is empty; else
            ``operational``.
        """
        # 1. An unbuildable graph or a down CRITICAL provider = the collection cannot do its job.
        if not ingest_buildable or not search_buildable or cls.__critical_down(providers):
            return HealthVerdict.DOWN
        # 2. Critical providers are all fine — a down reranker or an empty index only DEGRADES.
        if cls.__noncritical_down(providers) or vector_count == 0:
            return HealthVerdict.DEGRADED
        # 3. Everything reachable and the index is populated.
        return HealthVerdict.OPERATIONAL

    @classmethod
    def search(
        cls,
        *,
        search_buildable: bool,
        providers: list[ProviderProbeResult],
        vector_count: int,
    ) -> SearchOperational:
        """
        Roll the search-side signals up into the tri-state search-operational verdict.

        Args:
            search_buildable (bool): Whether the search graph builds + validates.
            providers (list[ProviderProbeResult]): The search sweep (query embedder + reranker).
            vector_count (int): The collection's indexed vector count.

        Returns:
            SearchOperational: ``False`` when the search graph is unbuildable or the query embedder
            is down; ``"degraded"`` when the embedder is fine but the reranker is down or the index
            is empty; ``True`` otherwise.
        """
        # 1. No graph, or the query embedder cannot be reached — nothing can be served.
        if not search_buildable:
            return False
        embedders = [p for p in providers if p.family == "embed"]
        if not embedders or any(cls.__is_down(p) for p in embedders):
            return False
        # 2. Embedder healthy — a down reranker or an empty index degrades rather than blocks.
        if cls.__noncritical_down(providers) or vector_count == 0:
            return "degraded"
        # 3. Embedder healthy, reranker (if any) healthy, index populated.
        return True


__all__ = ["HealthVerdictResolver"]
