# ====== Code Summary ======
# The reusable ForEach-BODY builder for a fail-soft capability chain — the one place the
# "prep → ForEach(chain [+ fail-soft terminal]) → apply" body topology lives. Shared verbatim by the
# metagen (structgen) and contextualize (llm) stages, which differ only in family, the single loop
# field the chain head reads (``request`` vs ``prompt``), the output field, and which model-free
# terminal (``metagen_skip`` / ``keep_raw``) hangs off the chain's last exit. It wraps
# ChainFragmentBuilder (the intra-chain escalation topology) and adds the OPTIONAL fail-soft terminal
# wired OnFailure off the last step: present → the ForEach item survives (that request's fields drop /
# the chunk stays raw); absent → a last-step failure propagates as a loud ForEach item failure. The
# chain is failure-only escalation (non-scored). The terminal shares the chain's single consumed face
# and single-slot output artefact, so ``ForEach.item_type()`` still resolves uniformly.
#
# Layering: sits in build/ and imports ONLY base + build/blob + build/chain — never from ingest/, so
# both stage bodies reuse it without a cross-import.

# ====== Standard Library Imports ======
from dataclasses import dataclass

# ====== Internal Project Imports ======
from shared_libs.pipelines.base import FromGroupInput, OnFailure, Transition
from shared_libs.pipelines.build.blob import ActionNodeBlob, GroupNodeBlob
from shared_libs.pipelines.build.chain import ChainFragmentBuilder, ChainStepSpec


@dataclass(frozen=True)
class FailSoftTerminal:
    """
    The model-free terminal a fail-soft ForEach body hangs off the chain's last step OnFailure.

    Emitted only when the stage's on_error policy is its fail-soft mode; its presence is what turns a
    total chain failure into a surviving item (fields dropped / chunk kept raw) instead of a loud
    ForEach item failure. It shares the chain's single consumed face and single-slot output artefact.

    Attributes:
        node_id (str): The terminal node id inside the body group.
        family (str): The terminal node's family (e.g. ``metagen`` / ``contextualize``).
        kind (str): The terminal node's kind (e.g. ``metagen_skip`` / ``keep_raw``).
    """

    node_id: str
    family: str
    kind: str


class ForEachChainBodyBuilder:
    """Static builder of a fail-soft ForEach body: a failure-only chain plus an optional terminal."""

    def __new__(cls, *args: object, **kwargs: object) -> None:
        raise TypeError(
            "ForEachChainBodyBuilder is a static-only class and cannot be instantiated."
        )

    @classmethod
    def build(
        cls,
        *,
        body_id: str,
        chain_prefix: str,
        family: str,
        steps: list[ChainStepSpec],
        group_field: str,
        output_field: str,
        terminal: FailSoftTerminal | None,
    ) -> GroupNodeBlob:
        """
        Assemble the ForEach body group: the failure-only chain, plus a fail-soft terminal when asked.

        Args:
            body_id (str): The body group's id.
            chain_prefix (str): Id prefix for the chain step nodes (``f"{prefix}_{i}"``).
            family (str): The registry family every step draws its kind from.
            steps (list[ChainStepSpec]): The ordered provider steps (cheap → robust); each success is
                itself a body terminal producing the uniform single-slot output artefact.
            group_field (str): The loop field the chain head — and the fail-soft terminal — reads from
                the ForEach group input.
            output_field (str): The producer field the chain's convergence output reads.
            terminal (FailSoftTerminal | None): The fail-soft terminal to wire OnFailure off the chain's
                last step; ``None`` → no terminal (a last-step failure fails the item loudly).

        Returns:
            GroupNodeBlob: The ForEach body group.
        """
        # 1. The failure-only chain — each step reads the loop's single face; NON-scored (escalate on
        #    failure only). Every step, on success, is itself a body terminal producing the output.
        fragment = ChainFragmentBuilder.build(
            prefix=chain_prefix,
            family=family,
            steps=steps,
            step_inputs={group_field: FromGroupInput(field_name=group_field)},
            output_field=output_field,
            scored=False,
        )
        nodes: list = list(fragment.nodes)
        transitions: list[Transition] = list(fragment.transitions)
        bindings: dict[str, dict] = dict(fragment.bindings)

        # 2. The optional fail-soft terminal — the chain's last step routes here OnFailure when every
        #    provider has failed, so the item survives; it reads the same single face as the steps.
        if terminal is not None:
            nodes.append(
                ActionNodeBlob(id=terminal.node_id, family=terminal.family, kind=terminal.kind)
            )
            transitions.append(
                Transition(
                    from_node_id=fragment.exits[-1],
                    to_node_id=terminal.node_id,
                    condition=OnFailure(),
                )
            )
            bindings[terminal.node_id] = {group_field: FromGroupInput(field_name=group_field)}

        return GroupNodeBlob(id=body_id, nodes=nodes, transitions=transitions, bindings=bindings)


__all__ = ["FailSoftTerminal", "ForEachChainBodyBuilder"]
