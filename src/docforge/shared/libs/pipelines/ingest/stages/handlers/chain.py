# ====== Code Summary ======
# StageChainHandler — compiles set_chain onto a PipelineState: an enrich per-figure model-call site
# (slotted) or a slot-less stage chain (parse / embed fallback chain, metagen structgen ladder). Every
# rebuild carries omitted step secrets from the same provider (ChainSecretCarry) and goes through the
# shared family chain rules; an unknown kind is DATA (a notice, the chain unchanged), never a raise.

# ====== Local Project Imports ======
from ..chain_rules import ChainRules
from ..models import ChainStep, SetChain
from ..secret_carry import ChainSecretCarry
from ..spec import StageKey, StageSpecs
from ..state import ChainSpec, PipelineState
from .tables import CHAIN_STAGES, METAGEN_CHAINS


class StageChainHandler:
    """Static handler for the set_chain action (and the 1-step chain behind a chain-stage provider)."""

    def __new__(cls, *args: object, **kwargs: object) -> None:
        raise TypeError("StageChainHandler is a static-only class and cannot be instantiated.")

    @staticmethod
    def __set_enrich_chain(
        state: PipelineState, stage: str, slot: str, steps: list, notices: list[str]
    ) -> None:
        """Rebuild the chain at one enrich model-call site (the branch is recompiled on assembly)."""
        if stage != StageKey.ENRICH:
            notices.append(f"stage '{stage}' has no chains to set")
            return
        try:
            branch = StageSpecs.branch(slot)
        except KeyError:
            notices.append(f"unknown chain slot '{slot}'")
            return
        # An unknown step kind is DATA, not an exception — leave the chain unchanged with a notice.
        unknown = ChainRules.unknown_kind_notices(branch.family, steps)
        if unknown:
            notices.extend(unknown)
            return
        current = state.chains.get(slot)
        carried = ChainSecretCarry.carry(
            branch.family, current.steps if current else [], steps, notices
        )
        completed = ChainRules.complete_steps(branch.family, carried)
        state.chains[slot] = ChainSpec(family=branch.family, steps=completed)
        if not steps:
            notices.append(f"chain '{slot}' emptied — figures of this class will be skipped")

    @staticmethod
    def __rebuild_stage_chain(
        state: PipelineState,
        stage: str,
        field: str,
        family: str,
        steps: list,
        notices: list[str],
    ) -> None:
        """Apply the family-level chain rules and set a slot-less stage chain (parse / metagen)."""
        # 1. A chain must keep at least one provider — an empty chain would leave the stage without
        #    its step (parse) or its ladder (metagen), so keep the current chain and warn.
        if not steps:
            notices.append(f"stage '{stage}' needs at least one provider — kept the current chain")
            return
        # 2. Keep each re-stated provider's omitted secret (same provider only), then apply the shared
        #    family chain rules; an unknown kind leaves the chain unchanged.
        current: ChainSpec = getattr(state, field)
        carried = ChainSecretCarry.carry(family, current.steps, steps, notices)
        completed, chain_notices = ChainRules.resolve(family, carried)
        notices.extend(chain_notices)
        if completed is None:
            return
        setattr(state, field, ChainSpec(family=family, steps=completed))

    @classmethod
    def set_stage_chain(
        cls, state: PipelineState, stage: str, steps: list[ChainStep], notices: list[str]
    ) -> None:
        """
        Rebuild a slot-less stage chain — a chain-capable linear stage (parse) or a metagen ladder.

        Args:
            state (PipelineState): The state to mutate.
            stage (str): The stage whose chain is rebuilt.
            steps (list[ChainStep]): The proposed chain steps, best first.
            notices (list[str]): Collector for chain-rule / no-op notices.
        """
        mapping = (
            CHAIN_STAGES
            if stage in CHAIN_STAGES
            else (METAGEN_CHAINS if stage in METAGEN_CHAINS else None)
        )
        if mapping is None:
            notices.append(f"stage '{stage}' has no chain to set")
            return
        field, family = mapping[stage]
        cls.__rebuild_stage_chain(state, stage, field, family, steps, notices)

    @classmethod
    def apply(cls, state: PipelineState, action: SetChain, notices: list[str]) -> None:
        """
        Compile a ``set_chain`` action — an enrich per-figure site (slot), or the stage itself.

        Args:
            state (PipelineState): The state to mutate.
            action (SetChain): The action carrying the stage, optional slot and steps.
            notices (list[str]): Collector for chain-rule / no-op notices.
        """
        # A slot names an enrich per-figure model-call site; no slot means the stage IS the chain.
        if action.slot is None:
            cls.set_stage_chain(state, action.stage, action.steps, notices)
            return
        cls.__set_enrich_chain(state, action.stage, action.slot, action.steps, notices)


__all__ = ["StageChainHandler"]
