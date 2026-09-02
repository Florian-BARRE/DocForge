# ====== Code Summary ======
# HealthVerdictResolver — the pure roll-up of a collection's raw health signals (both graphs'
# buildability, the per-side provider sweeps, the vector count) into the headline the UI drives its
# banner from: an honest ``verdict`` plus a human-readable ``reason``, and the independent search
# ``search_operational`` tri-state. It encodes ONE policy in one place and, crucially, keeps four
# distinct realities apart that a binary up/down would conflate:
#   * empty  — providers reachable, graphs build, but nothing indexed yet (NEUTRAL, not a fault).
#   * ingest_unavailable — the ingest pipeline is structurally invalid, so NEW documents cannot be
#     ingested; an existing index is still searchable, so this is NOT a global outage.
#   * degraded — a provider actually used is unreachable/misconfigured (a real runtime fault).
#   * down — search itself cannot be served (broken search graph or unreachable query embedder).

# ====== Standard Library Imports ======
from dataclasses import dataclass

# ====== Third-Party Library Imports ======
from loggerplusplus import loggerplusplus

# ====== Internal Project Imports ======
from shared_libs.pipelines.reachability import ProbeStatus, ProviderProbeResult

# ====== Local Project Imports ======
from .models import HealthVerdict, SearchOperational

# The probe outcomes that mean a provider is unusable right now (a real reachability/credential
# failure). ``ok`` is healthy; ``skipped``/``not_configured`` mean there was nothing to reach.
_DOWN_STATUSES = frozenset({ProbeStatus.UNREACHABLE, ProbeStatus.AUTH_FAILED})

# The reranker is the one non-critical provider: search still returns (un-re-ranked) results without
# it, so a down reranker DEGRADES rather than takes the collection DOWN.
_NONCRITICAL_FAMILIES = frozenset({"rerank"})


@dataclass(frozen=True, slots=True)
class HealthRollup:
    """The rolled-up overall verdict plus the human-readable reason the banner shows."""

    verdict: HealthVerdict
    reason: str


class HealthVerdictResolver:
    """Static roll-up of raw health signals into the overall verdict/reason + the search verdict."""

    logger = loggerplusplus.bind(identifier="HealthVerdictResolver")

    def __new__(cls, *args: object, **kwargs: object) -> None:
        raise TypeError("HealthVerdictResolver is a static-only class and cannot be instantiated.")

    @staticmethod
    def __is_down(probe: ProviderProbeResult) -> bool:
        """Whether a probe outcome means the provider is unusable now."""
        return probe.status in _DOWN_STATUSES

    @classmethod
    def __first_down(cls, providers: list[ProviderProbeResult]) -> ProviderProbeResult | None:
        """The first unreachable/mis-authenticated provider, or None when all are usable."""
        return next((p for p in providers if cls.__is_down(p)), None)

    @classmethod
    def __query_embedder_down(cls, search_providers: list[ProviderProbeResult]) -> bool:
        """
        Whether the query embedder cannot be reached — the one provider search cannot do without.

        No embedder in the sweep at all (the collection wired none, or its embed blob is malformed
        so the rebuild yielded nothing) is treated as down: a query cannot be encoded either way.
        """
        embedders = [p for p in search_providers if p.family == "embed"]
        return not embedders or any(cls.__is_down(p) for p in embedders)

    @staticmethod
    def __down_reason(search_buildable: bool, search_providers: list[ProviderProbeResult]) -> str:
        """Explain WHY search cannot be served (broken graph vs unreachable/missing embedder)."""
        # 1. A structurally invalid search graph cannot run at all.
        if not search_buildable:
            return (
                "Search is unavailable — the collection's search pipeline is structurally invalid "
                "and must be repaired before any query can be served."
            )
        # 2. Otherwise the query embedder is the culprit: unreachable, or none configured.
        embedders = [p for p in search_providers if p.family == "embed"]
        down = next((p for p in embedders if p.status in _DOWN_STATUSES), None)
        if down is not None:
            return (
                f"Search is unavailable — the query embedder is unreachable "
                f"({down.kind}: {down.detail})."
            )
        return "Search is unavailable — the collection has no query embedder configured."

    @staticmethod
    def __ingest_unavailable_reason(vector_count: int) -> str:
        """Explain that ingestion is blocked while (possibly) leaving existing search intact."""
        base = (
            "New documents cannot be ingested — the ingestion pipeline is structurally invalid "
            "(fix the pipeline configuration to resume ingestion)"
        )
        if vector_count > 0:
            return base + "; search over the already-indexed documents still works."
        return base + "."

    @staticmethod
    def __degraded_reason(down: ProviderProbeResult) -> str:
        """Name the unreachable provider and the side of the pipeline it sits on."""
        side = "ingest" if down.side == "ingest" else "search"
        return (
            f"A required provider is unreachable — {side} node '{down.kind}' "
            f"({down.family}): {down.detail}."
        )

    @classmethod
    def overall(
        cls,
        *,
        ingest_buildable: bool,
        search_buildable: bool,
        ingest_providers: list[ProviderProbeResult],
        search_providers: list[ProviderProbeResult],
        vector_count: int,
    ) -> HealthRollup:
        """
        Roll the raw signals up into the overall verdict + a human-readable reason.

        The precedence is worst-actionable-first, and deliberately keeps "cannot ingest" apart from
        "cannot search": a collection with a broken ingest blob but a live index + working search is
        ``ingest_unavailable`` (still queryable), NOT ``down``.

        Args:
            ingest_buildable (bool): Whether the ingest graph builds + structurally validates.
            search_buildable (bool): Whether the search graph builds + structurally validates.
            ingest_providers (list[ProviderProbeResult]): The ingest-side reachability sweep.
            search_providers (list[ProviderProbeResult]): The search-side sweep (embedder + reranker).
            vector_count (int): The collection's indexed vector count.

        Returns:
            HealthRollup: The verdict (operational / empty / degraded / ingest_unavailable / down)
            and the reason string the UI surfaces as the banner's first line.
        """
        # 1. Search inoperable = the collection cannot answer queries at all → DOWN (its core job).
        if not search_buildable or cls.__query_embedder_down(search_providers):
            return HealthRollup(
                HealthVerdict.DOWN, cls.__down_reason(search_buildable, search_providers)
            )

        # 2. Search works, but the ingest graph is structurally invalid → new docs cannot be
        #    ingested. An existing index stays searchable, so this is NOT a global outage.
        if not ingest_buildable:
            return HealthRollup(
                HealthVerdict.INGEST_UNAVAILABLE, cls.__ingest_unavailable_reason(vector_count)
            )

        # 3. Both graphs build — a provider actually used being unreachable is a real runtime fault.
        down = cls.__first_down(ingest_providers + search_providers)
        if down is not None:
            return HealthRollup(HealthVerdict.DEGRADED, cls.__degraded_reason(down))

        # 4. Everything reachable and buildable, but nothing indexed yet → NEUTRAL empty/pending.
        if vector_count == 0:
            return HealthRollup(
                HealthVerdict.EMPTY,
                "No documents are indexed yet — the collection is ready to ingest.",
            )

        # 5. Index populated, providers reachable, both graphs build.
        return HealthRollup(
            HealthVerdict.OPERATIONAL,
            f"Operational — {vector_count} vectors indexed and all providers reachable.",
        )

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

        Independent of the overall verdict: it answers "can a query be served right now" for the UI's
        search box. An EMPTY index is NOT degraded here — search runs fine, it just returns nothing.

        Args:
            search_buildable (bool): Whether the search graph builds + validates.
            providers (list[ProviderProbeResult]): The search sweep (query embedder + reranker).
            vector_count (int): The collection's indexed vector count (unused for the tri-state now,
                kept for signature stability with the overall roll-up caller).

        Returns:
            SearchOperational: ``False`` when the search graph is unbuildable or the query embedder
            is down; ``"degraded"`` when the embedder is fine but the reranker is down; else ``True``.
        """
        _ = vector_count
        # 1. No graph, or the query embedder cannot be reached — nothing can be served.
        if not search_buildable or cls.__query_embedder_down(providers):
            return False
        # 2. Embedder healthy — a down reranker degrades (results are un-re-ranked) but still serve.
        reranker_down = any(
            p.family in _NONCRITICAL_FAMILIES and cls.__is_down(p) for p in providers
        )
        if reranker_down:
            return "degraded"
        # 3. Embedder healthy, reranker (if any) healthy — search serves.
        return True


__all__ = ["HealthVerdictResolver", "HealthRollup"]
