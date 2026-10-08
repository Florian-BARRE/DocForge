# ====== Code Summary ======
# StageProviderHandler — compiles set_provider onto a PipelineState. On a chain-capable stage (parse,
# embed) picking a provider is sugar for a 1-step chain; on a single-provider stage (chunk) it swaps
# the kind and resets the config to build-safe schema defaults.

# ====== Internal Project Imports ======
from shared_libs.pipelines.registry import NodeRegistry

# ====== Local Project Imports ======
from ..chain_rules import ChainRules
from ..models import ChainStep, SetProvider
from ..spec import StageSpecs
from ..state import PipelineState
from .chain import StageChainHandler
from .tables import CHAIN_STAGES, PROVIDERS


class StageProviderHandler:
    """Static handler for the set_provider action."""

    def __new__(cls, *args: object, **kwargs: object) -> None:
        raise TypeError("StageProviderHandler is a static-only class and cannot be instantiated.")

    @staticmethod
    def apply(state: PipelineState, action: SetProvider, notices: list[str]) -> None:
        """
        Swap an exclusive stage's kind and reset its config to build-safe schema defaults.

        Args:
            state (PipelineState): The state to mutate.
            action (SetProvider): The action carrying the stage and the provider kind.
            notices (list[str]): Collector for no-op / unknown-kind notices.
        """
        stage, kind = action.stage, action.kind
        meta = StageSpecs.meta(stage) if stage in {*PROVIDERS, *CHAIN_STAGES} else None
        # 1. A chain-capable provider stage (parse): picking a provider is sugar for a 1-step chain.
        if stage in CHAIN_STAGES:
            StageChainHandler.set_stage_chain(state, stage, [ChainStep(kind=kind)], notices)
            return
        # 2. A single-provider stage (chunk, embed): swap the kind, reset its config.
        if meta is None:
            notices.append(f"stage '{stage}' has no provider to set")
            return
        if kind not in NodeRegistry.kinds(meta.family or ""):
            notices.append(f"'{kind}' is not a '{meta.family}' provider")
            return
        kind_field, config_field = PROVIDERS[stage]
        setattr(state, kind_field, kind)
        setattr(state, config_field, ChainRules.reset_config(meta.family or "", kind))


__all__ = ["StageProviderHandler"]
