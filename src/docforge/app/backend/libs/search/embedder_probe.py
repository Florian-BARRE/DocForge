# ====== Code Summary ======
# QueryEmbedderProbe — classifies WHY a search query failed to encode, so the API can tell a caller
# "fix your config" from "retry shortly". When the search pipeline reports the query could not be
# embedded, this rebuilds the collection's query embedder from its stored pipeline blob (the SAME
# node that indexed the chunks — shared vector space) and runs a bounded reachability probe against
# it, projecting the outcome onto a ProbeStatus. It spends no real call (only node.preflight()), runs
# OUTSIDE the node (the node stays pure), and is capped by the sweep's own ~5s per-probe ceiling.

# ====== Third-Party Library Imports ======
from loggerplusplus import LoggerClass

# ====== Internal Project Imports ======
from config import RUNTIME_CONFIG
from shared_libs.pipelines.nodes.embed.blob import EmbedBlobResolver
from shared_libs.pipelines.reachability import (
    ProbeStatus,
    ProviderEgressPolicy,
    ReachabilitySweep,
)

# The side stamped on the query-embedder probe (it encodes the search query, not an ingest doc).
_SEARCH_SIDE = "search"


class QueryEmbedderProbe(LoggerClass):
    """
    Probes a collection's query embedder to classify a failed search encode as permanent vs transient.

    Stateless across calls — safe to construct per request. It rebuilds a THROWAWAY embedder from the
    stored blob (never wired into a graph) and delegates the actual probe to a shared ReachabilitySweep.
    """

    def __init__(self) -> None:
        LoggerClass.__init__(self)
        self._sweep = ReachabilitySweep()
        # The SAME egress allowlist the collection-health sweep enforces. This READ-scoped classifier
        # rebuilds an embedder from a caller-influenced ``base_url`` and probes it, so without the gate
        # it is a parallel SSRF scanner of the internal network (empty allowlist = allow-all, OFF).
        self._egress_policy = ProviderEgressPolicy.from_spec(
            RUNTIME_CONFIG.PROVIDER_EGRESS_ALLOWLIST
        )

    async def classify(self, pipeline_blob: dict) -> ProbeStatus:
        """
        Classify a search encode failure by probing the collection's query embedder.

        Args:
            pipeline_blob (dict): The collection's serialised INGEST pipeline blob — it carries the
                embed node whose endpoint the query is encoded through (the shared vector space).

        Returns:
            ProbeStatus: ``unreachable`` (dead host / transport error / drifted blob) or
            ``auth_failed`` (rejected credentials) for a PERMANENT config issue; ``ok`` when the
            embedder answers — so the original failure was genuinely transient; ``not_configured``
            when the blob carries no embed node.
        """
        # 1. No embed node in the blob → there is nothing to reach (a structural, not transient, gap).
        embed_node = EmbedBlobResolver.find_embed_node(pipeline_blob)
        if embed_node is None:
            return ProbeStatus.NOT_CONFIGURED

        # 2. Rebuild the query embedder from its stored config; a drifted blob (extra="forbid") is a
        #    permanent config problem, surfaced as ``unreachable`` rather than crashing the classifier.
        try:
            embedder, _ = EmbedBlobResolver.rebuild(
                embed_node["kind"],
                dict(embed_node.get("config", {})),
                node_id=embed_node.get("id") or "encode",
            )
        except Exception as exc:  # noqa: BLE001 — a bad blob must classify, not 500 the search route.
            self.logger.warning(f"Query embedder rebuild failed: {type(exc).__name__}: {exc}")
            return ProbeStatus.UNREACHABLE

        # 3. Probe the throwaway embedder under the sweep's bounded cap AND the egress allowlist (a
        #    disallowed host is reported ``blocked``, never probed); its status IS the verdict.
        results = await self._sweep.probe_nodes([embedder], _SEARCH_SIDE, self._egress_policy)
        return results[0].status if results else ProbeStatus.SKIPPED


__all__ = ["QueryEmbedderProbe"]
