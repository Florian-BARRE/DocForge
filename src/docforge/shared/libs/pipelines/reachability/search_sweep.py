# ====== Code Summary ======
# SearchReachabilitySweep — the search-side counterpart of the ingest ReachabilitySweep. A search
# graph's provider reachability lives in two places: the QUERY EMBEDDER endpoint is carried by the
# collection's OWN embed node in its ingest pipeline blob (the query must encode in the SAME vector
# space the chunks were indexed with), while the RERANK endpoint is a leaf of the built search graph.
# This helper composes both into one provider list — the query embedder (always, when the collection
# has one) plus every provider-hosted search leaf (the reranker when present) — each stamped
# side="search". It reuses ReachabilitySweep for the actual probing; local search leaves (retrieve /
# hydrate / fuse / normalize / encode) carry no endpoint and are deliberately left out.

# ====== Third-Party Library Imports ======
from loggerplusplus import LoggerClass

# ====== Internal Project Imports ======
from shared_libs.pipelines.base import Group
from shared_libs.pipelines.nodes.embed.blob import EmbedBlobResolver

# ====== Local Project Imports ======
from .result import ProviderProbeResult
from .status import ProbeStatus
from .sweep import ReachabilitySweep

# The side every result of this helper is stamped with (mirrors the ingest sweep's "ingest").
_SEARCH_SIDE = "search"


class SearchReachabilitySweep(LoggerClass):
    """
    Sweeps a search graph's provider endpoints: the query embedder + the reranker (iff present).

    Stateless across sweeps. It never spends a real call — it resolves the query embedder from the
    collection's pipeline blob, collects the search graph's provider-hosted leaves, and delegates
    the probing to a shared ReachabilitySweep.
    """

    def __init__(self) -> None:
        LoggerClass.__init__(self)
        self._sweep = ReachabilitySweep()

    async def sweep(self, pipeline_blob: dict, search_graph: Group) -> list[ProviderProbeResult]:
        """
        Probe the search graph's providers: the query embedder + provider-hosted search leaves.

        Args:
            pipeline_blob (dict): The collection's serialised INGEST pipeline blob — it carries the
                embed node whose endpoint the query is encoded through (shared vector space).
            search_graph (Group): The built + validated search graph — its provider-hosted leaves
                (the reranker) are probed; local leaves (retrieve/hydrate/fuse/normalize/encode)
                carry no endpoint and are skipped.

        Returns:
            list[ProviderProbeResult]: The query embedder outcome (when the collection has an embed
            node) followed by one outcome per provider-hosted search leaf, all side="search".
        """
        # 1. The query embedder — rebuilt from the ingest blob (the node that indexed the chunks).
        nodes = []
        embed_node = EmbedBlobResolver.find_embed_node(pipeline_blob)
        if embed_node is not None:
            embedder, _ = EmbedBlobResolver.rebuild(
                embed_node["kind"],
                dict(embed_node.get("config", {})),
                node_id=embed_node.get("id") or "encode",
            )
            nodes.append(embedder)

        # 2. Every provider-hosted leaf of the search graph (the reranker when wired in).
        nodes.extend(
            leaf
            for leaf in self._sweep.collect_leaves(search_graph)
            if self._sweep.probes_endpoint(leaf)
        )

        # 3. Probe the composed provider set concurrently, all stamped side="search".
        results = await self._sweep.probe_nodes(nodes, _SEARCH_SIDE)

        # 4. Surface an EXPLICIT "no reranker" entry when the graph has none, so a consumer asking
        #    "is the reranker up?" gets "n/a — none configured" instead of silent absence.
        if not any(result.family == "rerank" for result in results):
            results.append(
                ProviderProbeResult(
                    node_id="rerank",
                    kind="cross_encoder",
                    family="rerank",
                    side=_SEARCH_SIDE,
                    status=ProbeStatus.NOT_CONFIGURED,
                    detail="no reranker configured in the search graph",
                    latency_ms=None,
                )
            )
        return results


__all__ = ["SearchReachabilitySweep"]
