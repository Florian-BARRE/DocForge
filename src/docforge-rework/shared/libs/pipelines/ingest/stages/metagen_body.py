# ====== Code Summary ======
# Builds the per-request ForEach BODY of a metagen stage from a structgen chain spec — the one place
# the metagen model-call topology lives. It is the SIMPLER sibling of EnrichBodyBuilder: no classifier
# switch, just one linear fallback chain. Each structgen step, on success, IS a terminal producing the
# body's uniform GeneratedValues artefact (an OnFailure edge escalates to the next provider). The
# on_error policy is a GRAPH EDGE, not a node flag: when it is skip_fields a model-free metagen_skip
# terminal is wired OnFailure off the chain's last step (the document survives, only that request's
# fields drop); when it is fail there is no such terminal, so a final-step failure propagates as a
# ForEach item failure — the document fails (the ForEach "item failure = loud failure" contract).

# ====== Internal Project Imports ======
from shared_libs.pipelines.base import FromGroupInput, OnFailure, Transition
from shared_libs.pipelines.build.blob import ActionNodeBlob, GroupNodeBlob
from shared_libs.pipelines.build.chain import ChainFragmentBuilder, ChainStepSpec
from shared_libs.pipelines.ingest.nodes.metagen.base import MetagenOnError

# ====== Local Project Imports ======
from .state import ChainSpec


class MetagenBodyBuilder:
    """Static builder of a metagen ForEach body from a structgen chain + the on_error policy."""

    BODY_ID = "metagen_path"
    CHAIN_PREFIX = "gen"
    SKIP_ID = "skip"
    OUTPUT_FIELD = "values"

    def __new__(cls, *args: object, **kwargs: object) -> None:
        raise TypeError("MetagenBodyBuilder is a static-only class and cannot be instantiated.")

    @classmethod
    def build(cls, chain: ChainSpec, on_error: MetagenOnError) -> GroupNodeBlob:
        """
        Assemble the per-request body: the structgen chain, plus a fail-soft skip terminal when asked.

        Args:
            chain (ChainSpec): The structgen chain (family ``structgen``, non-scored) whose steps
                each fulfil one GenerationRequest and produce the terminal GeneratedValues.
            on_error (MetagenOnError): skip_fields → append a model-free metagen_skip terminal wired
                OnFailure off the last step; fail → no terminal (a last-step failure fails the item).

        Returns:
            GroupNodeBlob: The ForEach body group (id ``metagen_path``).
        """
        # 1. The structgen chain — each step reads the loop's request; NON-scored (escalate on
        #    failure only). Every step, on success, is itself a body terminal producing GeneratedValues.
        fragment = ChainFragmentBuilder.build(
            prefix=cls.CHAIN_PREFIX,
            family=chain.family,
            steps=[
                ChainStepSpec(kind=step.kind, config=dict(step.config), score_below=step.score_below)
                for step in chain.steps
            ],
            step_inputs={"request": FromGroupInput(field_name="request")},
            output_field=cls.OUTPUT_FIELD,
            scored=False,
        )
        nodes: list = list(fragment.nodes)
        transitions: list[Transition] = list(fragment.transitions)
        bindings: dict[str, dict] = dict(fragment.bindings)

        # 2. skip_fields: the fail-soft terminal — the chain's last step routes here OnFailure when
        #    every provider has failed, so the document survives (only this request's fields drop).
        if on_error == MetagenOnError.SKIP_FIELDS:
            nodes.append(ActionNodeBlob(id=cls.SKIP_ID, family="metagen", kind="metagen_skip"))
            transitions.append(
                Transition(
                    from_node_id=fragment.exits[-1], to_node_id=cls.SKIP_ID, condition=OnFailure()
                )
            )
            bindings[cls.SKIP_ID] = {"request": FromGroupInput(field_name="request")}

        return GroupNodeBlob(
            id=cls.BODY_ID, nodes=nodes, transitions=transitions, bindings=bindings
        )


__all__ = ["MetagenBodyBuilder"]
