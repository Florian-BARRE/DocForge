# ====== Code Summary ======
# ReachabilitySweep — the ONE public, reusable reachability prober over a BUILT graph. Given a graph
# (or a flat set of action leaves) it walks the same node taxonomy the engine dispatches on —
# recursing groups and ForEach bodies — runs each provider leaf's preflight() under a short per-probe
# cap, and projects the outcome onto a ProviderProbeResult (ok / unreachable / auth_failed / skipped)
# with a latency and a human detail on failure. It is the single seam behind BOTH the worker's
# fail-fast ingest preflight (which raises on any failure) and the app's on-demand collection-health
# endpoint (which serialises the structured results). It runs OUTSIDE nodes — a node stays pure, the
# sweep only calls node.preflight(), which reads self.config. No DB/S3, no engine execution.

# ====== Standard Library Imports ======
import asyncio
from time import perf_counter

# ====== Third-Party Library Imports ======
from loggerplusplus import LoggerClass

# ====== Internal Project Imports ======
from shared_libs.pipelines.base import ActionNode, ForEach, Group
from shared_libs.pipelines.nodes.openai_compat import (
    EndpointAuthError,
    EndpointReachability,
    EndpointUnreachableError,
)
from shared_libs.pipelines.registry import NodeRegistry

# ====== Local Project Imports ======
from .result import ProviderProbeResult
from .status import ProbeStatus

# The outer per-probe cap is DERIVED from each node's own preflight budget (its
# ``preflight_timeout_seconds`` × the probe's retries) plus this slack, so it always sits ABOVE the
# probe's internal budget — the pre-fix bug was a fixed 5 s outer cap firing BEFORE the node's 10 s
# probe, defeating its retries. An absolute ceiling still guards against a pathological config so one
# hung endpoint cannot stall the concurrent sweep.
_PROBE_MARGIN_SECONDS = 2.0
_PROBE_CEILING_SECONDS = 60.0


class ReachabilitySweep(LoggerClass):
    """
    Probes every provider-hosted action leaf of a built graph for reachability + credentials.

    Stateless across sweeps — safe to share. It never mutates the graph nor spends a real call:
    it only invokes each leaf's ``preflight()`` (a cheap endpoint GET) and records the outcome.
    """

    def __init__(self) -> None:
        LoggerClass.__init__(self)

    @staticmethod
    def __detail(exc: Exception) -> str:
        """Format an exception into a compact, human-readable probe detail."""
        return f"{type(exc).__name__}: {exc}"

    @staticmethod
    def __probe_cap(node: ActionNode) -> float:
        """The outer wait_for for one node: above its own probe budget, under the absolute ceiling.

        Sized from the node's configured ``preflight_timeout_seconds`` so the probe's internal
        retries always finish before this cap fires; a node without the knob falls back to the
        probe's default budget. Clamped to the ceiling so a huge config cannot stall the sweep.
        """
        timeout = getattr(node.config, "preflight_timeout_seconds", None)
        budget = EndpointReachability.budget(timeout) if timeout else EndpointReachability.budget()
        return min(budget + _PROBE_MARGIN_SECONDS, _PROBE_CEILING_SECONDS)

    async def __probe(self, node: ActionNode, side: str) -> ProviderProbeResult:
        """
        Probe one action leaf, projecting its preflight() outcome onto a ProviderProbeResult.

        Mapping: no preflight override → ``skipped`` (a local leaf, nothing to reach); a rejected
        credential (EndpointAuthError) → ``auth_failed``; a transport failure or per-probe timeout
        (EndpointUnreachableError / TimeoutError) → ``unreachable``; any other preflight exception
        → ``unreachable`` (the endpoint is not usable before spend); success → ``ok``.

        Args:
            node (ActionNode): The built action leaf to probe.
            side (str): Which pipeline it belongs to ('ingest' or 'search'), stamped on the result.

        Returns:
            ProviderProbeResult: The structured outcome for this leaf.
        """
        family = NodeRegistry.family_of(type(node))
        # The provider's base URL is secret-free (the api_key is a separate config field) — surface
        # it so a health dashboard can name WHICH endpoint each stage points at.
        endpoint = getattr(node.config, "base_url", None)

        # 1. A leaf with no preflight override has no endpoint to reach — nothing to probe.
        if not self.probes_endpoint(node):
            return ProviderProbeResult(
                node_id=node.id,
                kind=node.KIND,
                family=family,
                side=side,
                status=ProbeStatus.SKIPPED,
            )

        # 2. Run the provider's own preflight under a short cap; time the round-trip either way.
        start = perf_counter()
        status, detail = ProbeStatus.OK, None
        try:
            await asyncio.wait_for(node.preflight(), timeout=self.__probe_cap(node))
        except EndpointAuthError as exc:
            status, detail = ProbeStatus.AUTH_FAILED, self.__detail(exc)
        except (EndpointUnreachableError, TimeoutError) as exc:
            status, detail = ProbeStatus.UNREACHABLE, self.__detail(exc)
        except Exception as exc:  # noqa: BLE001 — any preflight failure = not usable before spend.
            status, detail = ProbeStatus.UNREACHABLE, self.__detail(exc)
        latency_ms = int((perf_counter() - start) * 1000)

        # 3. Assemble the structured record (detail only on a non-ok outcome).
        return ProviderProbeResult(
            node_id=node.id,
            kind=node.KIND,
            family=family,
            side=side,
            status=status,
            endpoint=endpoint,
            detail=detail,
            latency_ms=latency_ms,
        )

    @staticmethod
    def probes_endpoint(node: ActionNode) -> bool:
        """
        Whether a leaf reaches an endpoint — i.e. it overrides the no-op ``ActionNode.preflight``.

        Args:
            node (ActionNode): The action leaf to test.

        Returns:
            bool: True when the node has a provider preflight to run (a provider-hosted leaf).
        """
        return type(node).preflight is not ActionNode.preflight

    @staticmethod
    def collect_leaves(group: Group) -> list[ActionNode]:
        """
        Collect every ActionNode in a built graph, recursing groups and ForEach bodies.

        Walks the SAME node taxonomy the engine dispatches on, so a provider nested inside a
        ForEach (e.g. a per-page VLM) is probed too — otherwise its unreachable endpoint would
        only surface mid-run.

        Args:
            group (Group): The built graph (or a nested sub-graph).

        Returns:
            list[ActionNode]: Every action leaf reachable from this group.
        """
        leaves: list[ActionNode] = []
        for child in group.children:
            if isinstance(child, Group):
                leaves.extend(ReachabilitySweep.collect_leaves(child))
            elif isinstance(child, ForEach):
                leaves.extend(ReachabilitySweep.collect_leaves(child.body))
            elif isinstance(child, ActionNode):
                leaves.append(child)
        return leaves

    async def probe_nodes(self, nodes: list[ActionNode], side: str) -> list[ProviderProbeResult]:
        """
        Probe a flat set of action leaves concurrently, one result per leaf.

        Args:
            nodes (list[ActionNode]): The action leaves to probe.
            side (str): Which pipeline they belong to ('ingest' or 'search'), stamped on results.

        Returns:
            list[ProviderProbeResult]: One outcome per leaf, in the input order.
        """
        if not nodes:
            return []
        return list(await asyncio.gather(*(self.__probe(node, side) for node in nodes)))

    async def sweep(self, group: Group, side: str) -> list[ProviderProbeResult]:
        """
        Sweep every action leaf of a built graph — provider leaves probed, local leaves skipped.

        Args:
            group (Group): The built + validated graph to sweep.
            side (str): Which pipeline it is ('ingest' or 'search'), stamped on every result.

        Returns:
            list[ProviderProbeResult]: One outcome per action leaf reachable from the graph.
        """
        return await self.probe_nodes(self.collect_leaves(group), side)


__all__ = ["ReachabilitySweep"]
