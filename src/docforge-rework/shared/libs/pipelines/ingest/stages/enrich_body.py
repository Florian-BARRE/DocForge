# ====== Code Summary ======
# Builds the per-figure ForEach BODY of the enrich stage from the classifier config and the chain
# specs — the one place the model-call topology lives. The classifier drives a when_equals switch
# per figure class; each class routes to its chain: an OCR chain reads scanned text and closes on a
# model-free figure_entry fed best-first (from_first), while a VLM chain describes visual figures and
# closes on a model-free vlm_entry — each provider produces a SCORED entry, the terminal projects it
# onto the uniform single-slot terminal. Between consecutive steps a score_below edge escalates on
# low quality and an on_failure edge falls through — exactly the chain semantics the stage view
# exposes. The decorative class routes to a zero-spend skip.

# ====== Internal Project Imports ======
from shared_libs.pipelines.base import (
    FromGroupInput,
    FromNode,
    OnSuccess,
    Transition,
    WhenEquals,
)
from shared_libs.pipelines.build.blob import ActionNodeBlob, GroupNodeBlob
from shared_libs.pipelines.build.chain import ChainFragment, ChainFragmentBuilder, ChainStepSpec
from shared_libs.public_models import FigureKind

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

        # 3. The decorative / fallback terminal — a visible, zero-spend skip every decorative class
        #    routes to (no chain, no model call).
        nodes.append(ActionNodeBlob(id=cls.SKIP_ID, family="enrich", kind="figure_entry"))
        for decorative_kind in StageSpecs.DECORATIVE_KINDS:
            transitions.append(cls.__switch(decorative_kind, cls.SKIP_ID))
        bindings[cls.SKIP_ID] = {"figure": FromNode(node_id=cls.CLASSIFY_ID, field_name="figure")}

        # 4. Build guard: every class the classifier can stamp MUST have an outgoing route, or the
        #    item would stall on 'classify' at run and fail the whole document. Reject at BUILD.
        cls.__assert_full_coverage(transitions)

        return GroupNodeBlob(
            id=cls.BODY_ID, nodes=nodes, transitions=transitions, bindings=bindings
        )

    @classmethod
    def __assert_full_coverage(cls, transitions: list[Transition]) -> None:
        """
        Fail the build when a classifier class has no outgoing when_equals route.

        Args:
            transitions (list[Transition]): The body transitions assembled so far.

        Raises:
            ValueError: When a FigureKind the classifier can emit is left unrouted — a wiring
                error that would otherwise stall the item at run and fail the whole document.
        """
        routed = {
            transition.condition.equals
            for transition in transitions
            if transition.from_node_id == cls.CLASSIFY_ID
            and isinstance(transition.condition, WhenEquals)
        }
        unrouted = {kind.value for kind in FigureKind} - routed
        if unrouted:
            raise ValueError(
                f"enrich body: classifier classes with no routing branch: {sorted(unrouted)}. "
                "Add a branch (via FIGURE_ROUTING) or mark the class decorative."
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
        """Append one class branch: its chain fragment, the entry switch and its terminal."""
        # 1. Build the provider chain fragment (step nodes, escalation edges, per-step bindings).
        #    OCR steps produce a raw scored `figure`; VLM steps produce a scored `entry`. Both are
        #    scored so a score_below edge can escalate between consecutive steps.
        frag = ChainFragmentBuilder.build(
            prefix=slot,
            family=chain.family,
            steps=[
                ChainStepSpec(kind=step.kind, config=dict(step.config), score_below=step.score_below)
                for step in chain.steps
            ],
            step_inputs={"figure": FromNode(node_id=cls.CLASSIFY_ID, field_name="figure")},
            output_field="figure" if chain.family == "ocr" else "entry",
            scored=True,
        )
        nodes.extend(frag.nodes)
        bindings.update(frag.bindings)

        # 2. Site concern — enter the branch on the routed class, then splice the escalation edges.
        transitions.append(cls.__switch(figure_kind, frag.heads[0]))
        transitions.extend(frag.transitions)

        # 3. Close the branch on a model-free terminal projecting its scored output → single-slot
        #    entry: figure_entry for an OCR chain (from the read figure), vlm_entry for a VLM chain.
        if chain.family == "ocr":
            cls.__close_ocr(slot, frag, nodes, transitions, bindings)
        else:
            cls.__close_vlm(slot, frag, nodes, transitions, bindings)

    @classmethod
    def __close_ocr(
        cls, slot: str, frag: ChainFragment,
        nodes: list, transitions: list[Transition], bindings: dict[str, dict],
    ) -> None:
        """Close an OCR chain on a model-free figure_entry fed best-first by whichever step ran."""
        terminal_id = f"{slot}_entry"
        nodes.append(ActionNodeBlob(id=terminal_id, family="enrich", kind="figure_entry"))
        # Every step, on success, closes the branch on the shared terminal.
        for step_id in frag.exits:
            transitions.append(Transition(
                from_node_id=step_id, to_node_id=terminal_id, condition=OnSuccess()
            ))
        # The join reads whichever step produced — best-first, as computed by the fragment.
        bindings[terminal_id] = {"figure": frag.output}

    @classmethod
    def __close_vlm(
        cls, slot: str, frag: ChainFragment,
        nodes: list, transitions: list[Transition], bindings: dict[str, dict],
    ) -> None:
        """Close a VLM chain on a model-free vlm_entry fed best-first by whichever step described."""
        terminal_id = f"{slot}_entry"
        nodes.append(ActionNodeBlob(id=terminal_id, family="enrich", kind="vlm_entry"))
        # Every step, on success, closes the branch on the shared terminal.
        for step_id in frag.exits:
            transitions.append(Transition(
                from_node_id=step_id, to_node_id=terminal_id, condition=OnSuccess()
            ))
        # The join reads the scored entry of whichever step produced — best-first, score dropped.
        bindings[terminal_id] = {"entry": frag.output}


__all__ = ["EnrichBodyBuilder"]
