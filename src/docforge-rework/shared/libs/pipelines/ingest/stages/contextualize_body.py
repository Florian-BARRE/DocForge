# ====== Code Summary ======
# Builds the per-prompt ForEach BODY of the contextualize LLM stage from a generic-llm chain spec —
# the one place the contextualize model-call topology lives. It is the STACK-position sibling of
# MetagenBodyBuilder: no classifier switch, just one linear fallback chain reading the loop's
# situating prompt. Each llm step, on success, IS a terminal producing the body's uniform Completion
# artefact (an OnFailure edge escalates to the next provider). llm is NON-scored, so escalation is
# failure-only (no ScoreBelow). The on_error policy is a GRAPH EDGE, not a node flag: when it is
# keep_raw a model-free keep_raw terminal is wired OnFailure off the chain's last step (the chunk
# stays raw, the document survives); when it is fail there is no such terminal, so a final-step
# failure propagates as a ForEach item failure — the document fails (the ForEach loud-failure contract).

# ====== Internal Project Imports ======
from shared_libs.pipelines.base import FromGroupInput, OnFailure, Transition
from shared_libs.pipelines.build.blob import ActionNodeBlob, GroupNodeBlob
from shared_libs.pipelines.build.chain import ChainFragmentBuilder, ChainStepSpec
from shared_libs.pipelines.ingest.nodes.contextualize.base import OnChunkError

# ====== Local Project Imports ======
from .models import ChainSpec


class ContextualizeBodyBuilder:
    """Static builder of a contextualize ForEach body from a generic-llm chain + the on_error policy."""

    BODY_ID = "ctx_path"
    CHAIN_PREFIX = "ctx"
    KEEP_ID = "keep"
    OUTPUT_FIELD = "completion"

    def __new__(cls, *args: object, **kwargs: object) -> None:
        raise TypeError("ContextualizeBodyBuilder is a static-only class and cannot be instantiated.")

    @classmethod
    def build(cls, chain: ChainSpec, on_error: OnChunkError) -> GroupNodeBlob:
        """
        Assemble the per-prompt body: the generic-llm chain, plus a fail-soft keep_raw terminal when asked.

        Args:
            chain (ChainSpec): The generic ``llm`` chain (family ``llm``, non-scored) whose steps each
                fulfil the loop's situating prompt and produce the terminal Completion.
            on_error (OnChunkError): keep_raw → append a model-free keep_raw terminal wired OnFailure
                off the last step (the chunk stays raw); fail → no terminal (a last-step failure fails
                the item, so the document fails loudly).

        Returns:
            GroupNodeBlob: The ForEach body group (id ``ctx_path``).
        """
        # 1. The llm chain — each step reads the loop's prompt; NON-scored (escalate on failure only).
        #    Every step, on success, is itself a body terminal producing the uniform Completion.
        fragment = ChainFragmentBuilder.build(
            prefix=cls.CHAIN_PREFIX,
            family=chain.family,
            steps=[
                ChainStepSpec(kind=step.kind, config=dict(step.config), score_below=step.score_below)
                for step in chain.steps
            ],
            step_inputs={"prompt": FromGroupInput(field_name="prompt")},
            output_field=cls.OUTPUT_FIELD,
            scored=False,
        )
        nodes: list = list(fragment.nodes)
        transitions: list[Transition] = list(fragment.transitions)
        bindings: dict[str, dict] = dict(fragment.bindings)

        # 2. keep_raw: the fail-soft terminal — the chain's last step routes here OnFailure when every
        #    provider has failed, so the chunk stays raw (its apply _with_context no-ops on the empty
        #    completion) and the document survives.
        if on_error == OnChunkError.KEEP_RAW:
            nodes.append(ActionNodeBlob(id=cls.KEEP_ID, family="contextualize", kind="keep_raw"))
            transitions.append(
                Transition(
                    from_node_id=fragment.exits[-1], to_node_id=cls.KEEP_ID, condition=OnFailure()
                )
            )
            bindings[cls.KEEP_ID] = {"prompt": FromGroupInput(field_name="prompt")}

        return GroupNodeBlob(
            id=cls.BODY_ID, nodes=nodes, transitions=transitions, bindings=bindings
        )


__all__ = ["ContextualizeBodyBuilder"]
