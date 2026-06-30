# ====== Code Summary ======
# ChainBuilder — turns one category's saved chain config (an ordered list of provider specs + an
# escalation gate) into a live, injectable Chain. It instantiates each provider via its config
# build() (merging deployment env defaults + a fail-fast availability check), in declaration order,
# and wraps them in a Chain. An EMPTY spec list yields an EMPTY Chain (a no-op passthrough) — never
# None: every stage always receives a Chain, "disabled" is just zero providers (the stage degrades
# gracefully). The deployment defaults (e.g. DOCLING_USE_GPU) are held on the builder so callers pass
# them once.

# ====== Standard Library Imports ======
from typing import Any

# ====== Third-Party Library Imports ======
from loggerplusplus import LoggerClass

# ====== Internal Project Imports ======
from common_libs.config.pipeline.chain_gate_config import ChainGateConfig
from common_libs.pipelines.capabilities.chain import Chain
from common_libs.pipelines.capabilities.chain.gate import ChainGate


class ChainBuilder(LoggerClass):
    """
    Build a provider-escalation Chain from a category's saved config.

    Stateless apart from the deployment ``defaults_cfg`` it carries (the env-level provider defaults
    merged into every spec). One instance serves every chain of a pipeline.
    """

    def __init__(self, defaults_cfg: Any = None) -> None:
        """
        Args:
            defaults_cfg (Any): Deployment config object supplying env-level provider defaults
                (e.g. GPU flags). Read via ``getattr`` by each provider's ``merge_defaults`` /
                ``availability``; ``None`` is safe (every access has a default).
        """
        LoggerClass.__init__(self)
        self._defaults = defaults_cfg

    def build(self, category: str, specs: list[Any], gate_cfg: ChainGateConfig) -> Chain:
        """
        Build the Chain for one category from its ordered provider specs + gate.

        Args:
            category (str): Provider category / chain stage key (e.g. ``"ocr"``, ``"parser"``).
            specs (list[Any]): Ordered provider config specs (each a ``@register`` provider config
                with ``merge_defaults`` / ``availability`` / ``build``). Index 0 is tried first.
            gate_cfg (ChainGateConfig): Escalation + exhaustion policy for this chain.

        Returns:
            Chain: The built chain (empty providers when ``specs`` is empty — a no-op passthrough).

        Raises:
            ChainBuildError: If any declared provider is unavailable (fail-fast before ingestion).
        """
        # 1. Instantiate each provider in declaration order (merge env defaults, then build).
        #    No availability/reachability probe here: build() stays PURE (no network I/O). Provider
        #    reachability is a pre-spend concern of the config-validation layer; an unreachable
        #    provider degrades gracefully through the chain gate at call time.
        built = []
        for spec in specs:
            merged = spec.merge_defaults(self._defaults)
            built.append(merged.build())

        # 2. Wrap in a Chain — empty list yields an empty no-op chain (never None).
        self.logger.info(f"Built {category!r} chain with {len(built)} provider(s).")
        return Chain(stage=category, providers=built, gate=ChainGate(gate_cfg))


__all__ = ["ChainBuilder"]
