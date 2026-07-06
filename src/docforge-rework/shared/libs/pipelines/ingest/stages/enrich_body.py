# ====== Code Summary ======
# Builds the per-figure ForEach BODY of the enrich stage from the classifier config and the chain
# specs — the one place the model-call topology lives. The classifier drives a when_equals switch
# per figure class; each class routes to its chain: an OCR chain reads scanned text and closes on a
# model-free figure_entry fed best-first (from_first), while a VLM chain describes visual figures
# (each provider produces the terminal entry itself). Between consecutive steps a score_below edge
# escalates on low quality and an on_failure edge falls through — exactly the chain semantics the
# stage view exposes. The decorative class routes to a zero-spend skip.

# ====== Internal Project Imports ======
from shared_libs.pipelines.base import (
    FromFirst,
    FromGroupInput,
    FromNode,
    OnFailure,
    OnSuccess,
    ScoreBelow,
    Transition,
    WhenEquals,
)
from shared_libs.pipelines.build.blob import ActionNodeBlob, GroupNodeBlob

# ====== Local Project Imports ======
from .spec import StageSpecs
from .state import ChainSpec


class EnrichBodyBuilder:
    """Static builder of the enrich ForEach body from classifier config + chain specs."""

    BODY_ID = "figure_path"
    CLASSIFY_ID = "classify"
    SKIP_ID = "entry"

    def __new__(cls, *args: object, **kwargs: object) -> None:
        raise TypeError("EnrichBodyBuilder is a static-only class and cannot be instantiated.")

    @classmethod
    def build(cls, classify_config: dict, chains: dict[str, ChainSpec]) -> GroupNodeBlob:
        """
        Assemble the per-figure body: classifier → per-class chains → uniform entry terminals.

        Args:
            classify_config (dict): The figure classifier's config.
            chains (dict[str, ChainSpec]): The chains, keyed by branch slot.

        Returns:
            GroupNodeBlob: The ForEach body group (id ``figure_path``).
        """
        # 1. The classifier — the switch driver every figure enters through.
        nodes: list = [
            ActionNodeBlob(
                id=cls.CLASSIFY_ID, family="enrich", kind="figure_classify",
                config=dict(classify_config),
            )
        ]
        transitions: list[Transition] = []
        bindings: dict[str, dict] = {
            cls.CLASSIFY_ID: {"figure": FromGroupInput(field_name="figure")}
        }

        # 2. One branch per figure class — a real chain, or a route to the skip when empty.
        for branch in StageSpecs.FIGURE_BRANCHES:
            chain = chains.get(branch.slot)
            if chain is None or not chain.steps:
                transitions.append(cls.__switch(branch.figure_kind, cls.SKIP_ID))
                continue
            cls.__append_branch(branch.slot, branch.figure_kind, chain, nodes, transitions, bindings)

        # 3. The decorative / fallback terminal — a visible, zero-spend skip.
        nodes.append(ActionNodeBlob(id=cls.SKIP_ID, family="enrich", kind="figure_entry"))
        transitions.append(cls.__switch(StageSpecs.DECORATIVE_KIND, cls.SKIP_ID))
        bindings[cls.SKIP_ID] = {"figure": FromNode(node_id=cls.CLASSIFY_ID, field_name="figure")}

        return GroupNodeBlob(
            id=cls.BODY_ID, nodes=nodes, transitions=transitions, bindings=bindings
        )

    @classmethod
    def __switch(cls, figure_kind: str, to_node_id: str) -> Transition:
        """A when_equals edge from the classifier routing one figure class to a branch head."""
        return Transition(
            from_node_id=cls.CLASSIFY_ID, to_node_id=to_node_id,
            condition=WhenEquals(field="kind", equals=figure_kind),
        )

    @classmethod
    def __append_branch(
        cls, slot: str, figure_kind: str, chain: ChainSpec,
        nodes: list, transitions: list[Transition], bindings: dict[str, dict],
    ) -> None:
        """Append one class branch: its chain nodes, escalation edges and terminal."""
        # 1. The chain's provider nodes, each reading the classified figure.
        step_ids = [f"{slot}_{index}" for index in range(len(chain.steps))]
        for step_id, step in zip(step_ids, chain.steps, strict=True):
            nodes.append(
                ActionNodeBlob(id=step_id, family=chain.family, kind=step.kind, config=dict(step.config))
            )
            bindings[step_id] = {"figure": FromNode(node_id=cls.CLASSIFY_ID, field_name="figure")}

        # 2. Enter the branch on the routed class; escalate step→step on low score, fall through
        #    on failure — the last step is the final say.
        transitions.append(cls.__switch(figure_kind, step_ids[0]))
        for current_id, next_id, step in zip(step_ids, step_ids[1:], chain.steps, strict=False):
            if step.score_below is not None:
                transitions.append(Transition(
                    from_node_id=current_id, to_node_id=next_id,
                    condition=ScoreBelow(threshold=step.score_below),
                ))
            transitions.append(Transition(
                from_node_id=current_id, to_node_id=next_id, condition=OnFailure()
            ))

        # 3. Close the branch on its terminal artefact (EnrichmentEntry).
        if chain.family == "ocr":
            cls.__close_ocr(slot, step_ids, nodes, transitions, bindings)
        # VLM/LLM providers each produce the terminal entry themselves — nothing to add.

    @classmethod
    def __close_ocr(
        cls, slot: str, step_ids: list[str],
        nodes: list, transitions: list[Transition], bindings: dict[str, dict],
    ) -> None:
        """Close an OCR chain on a model-free figure_entry fed best-first by whichever step ran."""
        terminal_id = f"{slot}_entry"
        nodes.append(ActionNodeBlob(id=terminal_id, family="enrich", kind="figure_entry"))
        # Every step, on success, closes the branch on the shared terminal.
        for step_id in step_ids:
            transitions.append(Transition(
                from_node_id=step_id, to_node_id=terminal_id, condition=OnSuccess()
            ))
        # The join reads the FIRST candidate that produced — best (last) step first.
        bindings[terminal_id] = {
            "figure": FromFirst(candidates=[
                FromNode(node_id=step_id, field_name="figure")
                for step_id in reversed(step_ids)
            ])
        }


__all__ = ["EnrichBodyBuilder"]
