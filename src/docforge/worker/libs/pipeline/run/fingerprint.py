# ====== Code Summary ======
# NodeFingerprintHelpers — the Merkle node fingerprint for a NODE_CACHED stage of the flow ingest
# pipeline. A stage's fingerprint folds: the stage id + a code version, its ``fingerprint_params`` (for
# parse: the parser-NODE identities, since the parsers are nodes not a chain), the SIGNATURES of every
# provider chain the stage still uses as an injected service (enrich: classifier / ocr / vlm via
# ``chain.signature()`` from the run registry), and the ordered UPSTREAM NODE_CACHED fingerprints it
# consumes (ingest -> parse -> enrich, a linear spine). Swapping a parser / provider / model / config
# changes a param or a chain signature, which changes the fingerprint, which busts the node cache. The
# actual Merkle hash is delegated to the ported ``compute_fingerprint``.

# ====== Third-Party Library Imports ======
from loggerplusplus import loggerplusplus

# ====== Internal Project Imports ======
from common_libs.pipelines.capabilities.caches import compute_fingerprint
from common_libs.pipelines.flow import Node, ServiceRegistry

# Single code version for the v2 node-engine stages (bump to force a global node-cache invalidation).
_CODE_VERSION: str = "2.0"


class NodeFingerprintHelpers:
    """
    Static helper computing a NODE_CACHED stage's Merkle fingerprint for the worker node cache.

    The fingerprint is the cache key (alongside the document id + stage id) the worker's hooks read
    and write. It is recomputed at the start of every NODE_CACHED stage and accumulated per run so a
    downstream stage folds its upstream fingerprints (the Merkle property).
    """

    logger = loggerplusplus.bind(identifier="NodeFingerprint")

    # The upstream NODE_CACHED stages each cached stage consumes (the linear ingest spine), in order.
    UPSTREAM: dict[str, tuple[str, ...]] = {
        "ingest": (),
        "parse": ("ingest",),
        "enrich": ("ingest", "parse"),
    }

    # Provider-chain categories whose signatures fold into a stage's fingerprint (still injected as
    # services in v2). Resolved from the run registry as ``<category>_chain`` (the builder's naming).
    # Parse is ABSENT here — its parsers are NODES, folded via the stage's ``fingerprint_params``.
    STAGE_CHAIN_CATEGORIES: dict[str, tuple[str, ...]] = {
        "ingest": (),
        "parse": (),
        "enrich": ("classifier", "ocr", "vlm"),
    }

    def __new__(cls, *args: object, **kwargs: object) -> None:
        """Block instantiation — this is a static-only helper class."""
        raise TypeError("NodeFingerprintHelpers is a static-only class and cannot be instantiated.")

    @classmethod
    def compute(
        cls,
        node: Node,
        registry: ServiceRegistry,
        upstream_fingerprints: dict[str, str],
    ) -> str:
        """
        Compute a NODE_CACHED stage's Merkle fingerprint.

        Args:
            node (Node): The NODE_CACHED stage node (its id drives the chain set + params + upstream).
            registry (ServiceRegistry): The run service registry the chains resolve from
                (``<category>_chain``).
            upstream_fingerprints (dict[str, str]): Already-computed fingerprints of the upstream
                NODE_CACHED stages, keyed by stage id (the per-run accumulator).

        Returns:
            str: The blake3 Merkle fingerprint (64-char hex digest).
        """
        # 1. Identity + a code version (cache-busting handle for the whole node-engine).
        key = node.id

        # 2. Params: the stage's own fingerprint knobs + the provider-chain signatures it uses.
        params = cls._stage_params(node, registry)

        # 3. Ordered upstream fingerprints: the NODE_CACHED stages this one consumes (Merkle edge).
        inputs = [
            upstream_fingerprints[producer]
            for producer in cls.UPSTREAM.get(key, ())
            if producer in upstream_fingerprints
        ]
        fingerprint = compute_fingerprint(key, _CODE_VERSION, params, inputs)
        self_chains = params.get("chain_signatures")
        self_params = {k: v for k, v in params.items() if k != "chain_signatures"}
        cls.logger.debug(
            f"Fingerprint {key!r}: code_version={_CODE_VERSION} chains={self_chains} "
            f"params={self_params} inputs={len(inputs)} -> {fingerprint[:8]}..."
        )
        return fingerprint

    @classmethod
    def _stage_params(cls, node: Node, registry: ServiceRegistry) -> dict:
        """
        Build the canonical fingerprint params of a NODE_CACHED stage.

        Merges the stage's own ``fingerprint_params`` (parse: the parser-node identities) with the
        per-category provider-chain signatures resolved from the registry (enrich: classifier/ocr/vlm).
        The two mechanisms reflect the v2 reality: parse providers are nodes (reachable on the stage),
        enrich providers are run-time injected chains (only reachable from the registry).

        Args:
            node (Node): The stage node.
            registry (ServiceRegistry): The run service registry the chains resolve from.

        Returns:
            dict: JSON-serialisable params ``{**stage_knobs, "chain_signatures": {category: sig}}``.
        """
        # 1. Stage-declared cache-busting knobs (parse: parser-node identities; others: none).
        params: dict = {}
        fingerprint_params = getattr(node, "fingerprint_params", None)
        if callable(fingerprint_params):
            params.update(fingerprint_params())

        # 2. Provider-chain signatures for every category this stage injects as a service (empty -> "").
        signatures: dict[str, str] = {}
        for category in cls.STAGE_CHAIN_CATEGORIES.get(node.id, ()):
            chain = registry.get(f"{category}_chain")
            signatures[category] = chain.signature() if chain is not None else ""
        params["chain_signatures"] = signatures
        return params


__all__ = ["NodeFingerprintHelpers"]
