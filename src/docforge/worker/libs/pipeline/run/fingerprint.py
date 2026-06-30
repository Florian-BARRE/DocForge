# ====== Code Summary ======
# NodeFingerprintHelpers — the Merkle node fingerprint for a NODE_CACHED stage of the ingest pipeline.
# A stage's fingerprint folds: the stage key + its code_version, its own ``fingerprint_params`` (the
# stage-level cache-busting knobs / flags), the SIGNATURES of every provider chain the stage uses
# (parser / classifier / ocr / vlm via ``chain.signature()`` resolved from the run service registry),
# and the ordered UPSTREAM NODE_CACHED fingerprints it consumes. Swapping a provider/model/config
# under identical flags changes a chain signature, which changes the fingerprint, which busts the
# node cache. The actual Merkle hash is delegated to the ported ``compute_fingerprint``.

# ====== Third-Party Library Imports ======
from loggerplusplus import loggerplusplus

# ====== Internal Project Imports ======
from common_libs.pipelines import AbstractNode, ServiceRegistry
from common_libs.pipelines.capabilities.caches import compute_fingerprint


class NodeFingerprintHelpers:
    """
    Static helper computing a NODE_CACHED stage's Merkle fingerprint for the worker node cache.

    The fingerprint is the cache key (alongside the document id + stage key) the worker's hooks read
    and write. It is recomputed at the start of every NODE_CACHED stage and accumulated per run so a
    downstream stage folds its upstream fingerprints (the Merkle property).
    """

    logger = loggerplusplus.bind(identifier="NodeFingerprint")

    # The provider-chain categories whose signatures fold into each NODE_CACHED stage's fingerprint.
    # Resolved from the run service registry as ``<category>_chain`` (the builder's naming). A change
    # to any of these chains (provider id / version / config) busts that stage's cache.
    STAGE_CHAIN_CATEGORIES: dict[str, tuple[str, ...]] = {
        "ingest": (),
        "parse": ("parser",),
        "enrich": ("classifier", "ocr", "vlm"),
    }

    def __new__(cls, *args: object, **kwargs: object) -> None:
        """Block instantiation — this is a static-only helper class."""
        raise TypeError("NodeFingerprintHelpers is a static-only class and cannot be instantiated.")

    @classmethod
    def compute(
        cls,
        node: AbstractNode,
        registry: ServiceRegistry,
        upstream_fingerprints: dict[str, str],
    ) -> str:
        """
        Compute a NODE_CACHED stage's Merkle fingerprint.

        Args:
            node (AbstractNode): The NODE_CACHED stage node (its key drives the chain set + params).
            registry (ServiceRegistry): The run service registry the chains are resolved from
                (``<category>_chain``).
            upstream_fingerprints (dict[str, str]): Already-computed fingerprints of the upstream
                NODE_CACHED stages, keyed by stage key (the per-run accumulator).

        Returns:
            str: The blake3 Merkle fingerprint (64-char hex digest).
        """
        # 1. Identity + cache-busting code version (StageSpec carries ``code_version``).
        key = node.key
        code_version = getattr(node.SPEC, "code_version", "1.0")

        # 2. Params: the stage's own fingerprint knobs + the provider-chain signatures it uses.
        params = cls._stage_params(node, registry)

        # 3. Ordered upstream fingerprints: the NODE_CACHED siblings this stage consumes (Merkle edge).
        inputs = [
            upstream_fingerprints[producer]
            for producer in node.consumes()
            if producer in upstream_fingerprints
        ]
        fingerprint = compute_fingerprint(key, code_version, params, inputs)
        cls.logger.debug(
            f"Fingerprint {key!r}: code_version={code_version} "
            f"chains={params['chain_signatures']} inputs={len(inputs)} -> {fingerprint[:8]}…"
        )
        return fingerprint

    @classmethod
    def _stage_params(cls, node: AbstractNode, registry: ServiceRegistry) -> dict:
        """
        Build the canonical fingerprint params of a NODE_CACHED stage.

        Merges the stage's own ``fingerprint_params`` (flags / parse parity key) with the per-category
        provider-chain signatures resolved from the registry. The chain signatures are the authoritative
        provider-identity dimension: the stage itself cannot reach a run-time injected chain.

        Args:
            node (AbstractNode): The stage node.
            registry (ServiceRegistry): The run service registry the chains resolve from.

        Returns:
            dict: JSON-serialisable params ``{**stage_knobs, "chain_signatures": {category: sig}}``.
        """
        # 1. Stage-declared cache-busting knobs (enrich flags / parse ``parse_chain`` parity key).
        params: dict = {}
        fingerprint_params = getattr(node, "fingerprint_params", None)
        if callable(fingerprint_params):
            params.update(fingerprint_params())

        # 2. Provider-chain signatures for every category this stage uses (empty chain -> "").
        signatures: dict[str, str] = {}
        for category in cls.STAGE_CHAIN_CATEGORIES.get(node.key, ()):
            chain = registry.resolve(f"{category}_chain")
            signatures[category] = chain.signature() if chain is not None else ""
        params["chain_signatures"] = signatures
        return params


__all__ = ["NodeFingerprintHelpers"]
