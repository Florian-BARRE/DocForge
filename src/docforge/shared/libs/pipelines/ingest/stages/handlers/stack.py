# ====== Code Summary ======
# StageStackHandler — compiles set_stack onto a PipelineState: rebuilds the ordered contextualize
# stack (empty disables the stage). Each method's config is completed build-safe (the llm method's
# config edits its PREP node); the llm method additionally carries a generic-llm chain resolved
# through the shared chain rules, inheriting an omitted secret from the llm method previously at the
# same stack position.

# ====== Internal Project Imports ======
from shared_libs.pipelines.registry import NodeRegistry

# ====== Local Project Imports ======
from ..chain_rules import ChainRules
from ..models import ChainStep, SetStack, StackMethod
from ..secret_carry import ChainSecretCarry
from ..spec import StageKey
from ..state import ChainSpec, PipelineState


class StageStackHandler:
    """Static handler for the set_stack action."""

    def __new__(cls, *args: object, **kwargs: object) -> None:
        raise TypeError("StageStackHandler is a static-only class and cannot be instantiated.")

    @staticmethod
    def __resolve_llm_chain(
        method: StackMethod, previous: StackMethod | None, notices: list[str]
    ) -> StackMethod:
        """Apply the generic-llm family chain rules to an llm method's chain (non-scored, failure-only).

        An unknown step kind is DATA — the chain is left as proposed with a notice (completing it
        would raise). Otherwise the steps are completed build-safe, any score threshold is stripped
        (llm is non-scored) and single-use repeats are flagged before the build rejects them. An
        omitted step secret is inherited from the same provider of the llm method previously at this
        stack position (``previous``), never from another kind.
        """
        chain = method.chain or ChainSpec(family="llm", steps=[ChainStep(kind="openai_compatible")])
        chain_steps = chain.steps or [ChainStep(kind="openai_compatible")]
        if previous is not None and previous.kind == "llm" and previous.chain is not None:
            chain_steps = ChainSecretCarry.carry("llm", previous.chain.steps, chain_steps, notices)
        completed, chain_notices = ChainRules.resolve("llm", chain_steps)
        notices.extend(chain_notices)
        # An unknown kind (completed is None) keeps the proposed steps as-is; else the completed ones.
        steps = chain_steps if completed is None else completed
        return method.model_copy(update={"chain": ChainSpec(family="llm", steps=steps)})

    @classmethod
    def apply(cls, state: PipelineState, action: SetStack, notices: list[str]) -> None:
        """
        Rebuild the ordered contextualize stack (empty disables the stage).

        Args:
            state (PipelineState): The state to mutate.
            action (SetStack): The action carrying the stage and the ordered stack methods.
            notices (list[str]): Collector for chain-rule / no-op notices.
        """
        stage, steps = action.stage, action.steps
        # 1. Only the contextualize stage carries a stack.
        if stage != StageKey.CONTEXTUALIZE:
            notices.append(f"stage '{stage}' has no stack to set")
            return
        # 2. An unknown method kind is DATA, not an exception — completing its config would call
        #    NodeRegistry.get and RAISE, so leave the stack unchanged with a notice (as every sibling
        #    chain/provider edit does; this is the one path the P3 guard had missed).
        available = set(NodeRegistry.kinds("contextualize"))
        unknown = [step.kind for step in steps if step.kind not in available]
        if unknown:
            notices.extend(f"'{kind}' is not a 'contextualize' method" for kind in unknown)
            return
        # 3. Complete every method build-safe; the llm method also resolves its chain.
        resolved: list = []
        for index, step in enumerate(steps):
            method = step.model_copy(
                update={
                    "config": {**ChainRules.reset_config("contextualize", step.kind), **step.config}
                }
            )
            if step.kind == "llm":
                previous = state.stack[index] if index < len(state.stack) else None
                method = cls.__resolve_llm_chain(method, previous, notices)
            resolved.append(method)
        state.stack = resolved
        if not steps:
            notices.append("contextualize stack emptied — chunks carry no added context")


__all__ = ["StageStackHandler"]
