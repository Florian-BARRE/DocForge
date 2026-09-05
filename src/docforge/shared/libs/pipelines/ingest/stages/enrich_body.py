# ====== Code Summary ======
# Builds the per-figure ForEach BODY of the enrich stage — the one place the model-call topology
# lives. Two modes: in ``classified`` (the stock mode) the classifier drives a when_equals switch per
# figure class and each class routes to its chain: an OCR chain reads scanned text and closes on a
# model-free figure_entry fed best-first (from_first), while a VLM chain describes visual figures and
# closes on a model-free vlm_entry — each provider produces a SCORED entry the terminal projects onto
# the uniform single-slot terminal, the decorative class routes to a zero-spend skip. In ``uniform``
# there is NO classifier and NO switch: every figure runs ONE treatment — an OCR chain (read text,
# closing on figure_entry) or a VLM chain (describe the image, closing on vlm_entry) — with a fail-soft
# on_failure skip so an un-enriched figure still passes through. Between
# consecutive chain steps a score_below edge escalates on low quality and an on_failure edge falls
# through — exactly the chain semantics the stage view exposes.

# ====== Internal Project Imports ======
from shared_libs.pipelines.base import (
    FromGroupInput,
    FromNode,
    OnFailure,
    OnSuccess,
    Transition,
    WhenEquals,
)
from shared_libs.pipelines.build.blob import ActionNodeBlob, GroupNodeBlob
from shared_libs.pipelines.build.chain import ChainFragment, ChainFragmentBuilder, ChainStepSpec
from shared_libs.public_models import FigureKind

# ====== Local Project Imports ======
from .spec import StageSpecs
from .state import _VLM_ENDPOINT, ChainSpec


class EnrichBodyBuilder:
    """Static builder of the enrich ForEach body from classifier config + chain specs."""

    BODY_ID = "figure_path"
    CLASSIFY_ID = "classify"
    SKIP_ID = "entry"
    # The classified-branch fail-soft terminal: a whole chain (VLM/OCR) failed AFTER a successful
    # classify, so the figure must pass through carrying the kind the classifier already stamped (and
    # any OCR read text it accumulated), NOT the raw ForEach item. Distinct from SKIP_ID, which also
    # serves the classifier's OWN failure — where no classified figure exists to read from.
    FAILSOFT_ID = "failsoft"
    # The uniform-mode single-treatment slots: an OCR chain (read text) or a VLM chain (describe).
    UNIFORM_OCR_SLOT = "scanned_text_ocr"
    UNIFORM_VLM_SLOT = "figure_describe_vlm"
    UNIFORM_PREFIX = "figure_uniform"
    UNIFORM_ENTRY_ID = "uniform_entry"
    # Default prompt when a fresh uniform-vlm chain has no user prompt yet (a plain describe).
    DESCRIBE_PROMPT = "Describe this image precisely, for retrieval purposes."

    def __new__(cls, *args: object, **kwargs: object) -> None:
        raise TypeError("EnrichBodyBuilder is a static-only class and cannot be instantiated.")

    @classmethod
    def build(
        cls,
        classify_config: dict,
        chains: dict[str, ChainSpec],
        mode: str = "classified",
        uniform_treatment: str = "ocr",
    ) -> GroupNodeBlob:
        """
        Assemble the per-figure body for the selected enrich mode.

        Args:
            classify_config (dict): The figure classifier's config (classified mode only).
            chains (dict[str, ChainSpec]): The chains, keyed by branch slot.
            mode (str): ``classified`` (classifier → per-class chains) or ``uniform`` (a single
                treatment every figure runs, no classifier, no switch). ``ocr_only`` is the legacy
                name of ``uniform`` and is accepted here.
            uniform_treatment (str): In ``uniform`` mode, the single treatment — ``ocr`` (read text)
                or ``vlm`` (describe the image with a vision model).

        Returns:
            GroupNodeBlob: The ForEach body group (id ``figure_path``).
        """
        # 0. The classifier-free mode: ONE treatment for every figure, fail-soft to a skip terminal.
        if mode in ("uniform", "ocr_only"):
            return cls.__build_uniform(chains, uniform_treatment)
        # 1. The classifier — the switch driver every figure enters through.
        nodes: list = [
            ActionNodeBlob(
                id=cls.CLASSIFY_ID,
                family="enrich",
                kind="figure_classify",
                config=dict(classify_config),
            )
        ]
        transitions: list[Transition] = []
        bindings: dict[str, dict] = {
            cls.CLASSIFY_ID: {"figure": FromGroupInput(field_name="figure")}
        }

        # 2. One branch per figure class — a real chain, or a route to the skip when empty.
        has_chain_branch = False
        for branch in StageSpecs.FIGURE_BRANCHES:
            chain = chains.get(branch.slot)
            if chain is None or not chain.steps:
                transitions.append(cls.__switch(branch.figure_kind, cls.SKIP_ID))
                continue
            cls.__append_branch(
                branch.slot, branch.figure_kind, chain, nodes, transitions, bindings
            )
            has_chain_branch = True

        # 3. The decorative / fallback terminal — a visible, zero-spend skip every decorative class
        #    routes to (no chain, no model call).
        nodes.append(ActionNodeBlob(id=cls.SKIP_ID, family="enrich", kind="figure_entry"))
        for decorative_kind in StageSpecs.DECORATIVE_KINDS:
            transitions.append(cls.__switch(decorative_kind, cls.SKIP_ID))
        # The skip terminal reads the figure from the ForEach ITEM (always present), NOT from the
        # classifier's output — else the fail-soft edge below would route a FAILED classify here only
        # for this terminal to fail too on an unresolvable binding (classify produced nothing).
        bindings[cls.SKIP_ID] = {"figure": FromGroupInput(field_name="figure")}

        # 3b. Fail-soft at the classifier itself — figure_classify is a VLM call, so it too can fail
        #     (unreachable endpoint, transient error). Its failure must not sink the document: route
        #     it to the skip terminal so the figure passes through un-classified/un-enriched. Priority
        #     puts the when_equals class routes above this on_failure, so a successful classify still
        #     switches by class; only a failed one falls through.
        transitions.append(
            Transition(from_node_id=cls.CLASSIFY_ID, to_node_id=cls.SKIP_ID, condition=OnFailure())
        )

        # 3c. The classified-branch fail-soft terminal — added only when a real chain branch exists
        #     (its sole incoming edges are those branches' tail on_failure). It reads the CLASSIFIER's
        #     stamped figure, so a figure whose whole chain failed keeps its classified kind and any
        #     OCR read text, instead of being reset to the raw item (PIPELINE.md: "VLM KO → kind
        #     conservé").
        if has_chain_branch:
            nodes.append(ActionNodeBlob(id=cls.FAILSOFT_ID, family="enrich", kind="figure_entry"))
            bindings[cls.FAILSOFT_ID] = {
                "figure": FromNode(node_id=cls.CLASSIFY_ID, field_name="figure")
            }

        # 4. Build guard: every class the classifier can stamp MUST have an outgoing route, or the
        #    item would stall on 'classify' at run and fail the whole document. Reject at BUILD.
        cls.__assert_full_coverage(transitions)

        return GroupNodeBlob(
            id=cls.BODY_ID, nodes=nodes, transitions=transitions, bindings=bindings
        )

    @classmethod
    def __build_uniform(cls, chains: dict[str, ChainSpec], treatment: str) -> GroupNodeBlob:
        """
        Assemble the classifier-free body: every figure runs ONE treatment, fail-soft to skip.

        The treatment is a single chain — an OCR chain (``treatment='ocr'``, read text, closing on a
        model-free ``figure_entry``) or a VLM chain (``treatment='vlm'``, describe the image with a
        configurable prompt, closing on a model-free ``vlm_entry``). Either way a failed chain
        fail-softs to a raw-figure skip so an un-enriched figure still passes through.

        Args:
            chains (dict[str, ChainSpec]): The chains, keyed by slot — ``scanned_text_ocr`` for the
                ocr treatment, ``figure_describe_vlm`` for the vlm treatment. An empty slot defaults
                to a single local rapidocr (ocr) or a single describe VLM step (vlm).
            treatment (str): ``ocr`` (read text) or ``vlm`` (describe with a vision model).

        Returns:
            GroupNodeBlob: The ForEach body group (id ``figure_path``).
        """
        # 1. Resolve the treatment into (slot, family, default step, terminal) — the ONE difference
        #    between reading text and describing the image; the wiring below is identical for both.
        if treatment == "vlm":
            slot, family, output_field, terminal_kind, terminal_field = (
                cls.UNIFORM_VLM_SLOT,
                "vlm",
                "entry",
                "vlm_entry",
                "entry",
            )
            # The endpoint stays the same opt-in placeholder the classified VLM branches ship with
            # (the user wires a real vision endpoint when they choose the vlm treatment).
            default_specs = [
                ChainStepSpec(
                    kind="openai_compatible",
                    config={**_VLM_ENDPOINT, "system_prompt": cls.DESCRIBE_PROMPT},
                )
            ]
        else:
            slot, family, output_field, terminal_kind, terminal_field = (
                cls.UNIFORM_OCR_SLOT,
                "ocr",
                "figure",
                "figure_entry",
                "figure",
            )
            default_specs = [ChainStepSpec(kind="rapidocr")]

        # 2. The single chain every figure runs — from the slot (escalation preserved), or the default.
        chain = chains.get(slot)
        if chain is not None and chain.steps:
            step_specs = [
                ChainStepSpec(kind=s.kind, config=dict(s.config), score_below=s.score_below)
                for s in chain.steps
            ]
        else:
            step_specs = default_specs
        frag = ChainFragmentBuilder.build(
            prefix=cls.UNIFORM_PREFIX,
            family=family,
            steps=step_specs,
            step_inputs={"figure": FromGroupInput(field_name="figure")},
            output_field=output_field,
            scored=True,
        )
        nodes: list = list(frag.nodes)
        transitions: list[Transition] = list(frag.transitions)
        bindings: dict[str, dict] = dict(frag.bindings)

        # 3. Success terminal — a model-free entry fed best-first by whichever step ran.
        nodes.append(ActionNodeBlob(id=cls.UNIFORM_ENTRY_ID, family="enrich", kind=terminal_kind))
        for step_id in frag.exits:
            transitions.append(
                Transition(
                    from_node_id=step_id, to_node_id=cls.UNIFORM_ENTRY_ID, condition=OnSuccess()
                )
            )
        bindings[cls.UNIFORM_ENTRY_ID] = {terminal_field: frag.output}

        # 4. Fail-soft skip — the whole chain failed, so pass the RAW figure through un-enriched (its
        #    binding reads the ForEach item, which always exists; the success terminal cannot serve
        #    here as its binding reads a step output that does not exist when every step failed).
        nodes.append(ActionNodeBlob(id=cls.SKIP_ID, family="enrich", kind="figure_entry"))
        bindings[cls.SKIP_ID] = {"figure": FromGroupInput(field_name="figure")}
        transitions.append(
            Transition(from_node_id=frag.exits[-1], to_node_id=cls.SKIP_ID, condition=OnFailure())
        )

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
            from_node_id=cls.CLASSIFY_ID,
            to_node_id=to_node_id,
            condition=WhenEquals(field="kind", equals=figure_kind),
        )

    @classmethod
    def __append_branch(
        cls,
        slot: str,
        figure_kind: str,
        chain: ChainSpec,
        nodes: list,
        transitions: list[Transition],
        bindings: dict[str, dict],
    ) -> None:
        """Append one class branch: its chain fragment, the entry switch and its terminal."""
        # 1. Build the provider chain fragment (step nodes, escalation edges, per-step bindings).
        #    OCR steps produce a raw scored `figure`; VLM steps produce a scored `entry`. Both are
        #    scored so a score_below edge can escalate between consecutive steps.
        frag = ChainFragmentBuilder.build(
            prefix=slot,
            family=chain.family,
            steps=[
                ChainStepSpec(
                    kind=step.kind, config=dict(step.config), score_below=step.score_below
                )
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

        # 4. Fail-soft: if the WHOLE chain fails (its most-robust step included, so no intra-chain
        #    fall-through is left), the figure must NOT sink the document. Route the tail's failure to
        #    the classified fail-soft terminal — the figure passes through un-enriched but KEEPS the
        #    kind the classifier stamped (and any OCR read text), reading the classifier's figure. The
        #    chain's own terminal cannot serve here: its binding reads the step output, which does not
        #    exist when every step failed.
        tail_id = frag.exits[-1]
        transitions.append(
            Transition(from_node_id=tail_id, to_node_id=cls.FAILSOFT_ID, condition=OnFailure())
        )

    @classmethod
    def __close_ocr(
        cls,
        slot: str,
        frag: ChainFragment,
        nodes: list,
        transitions: list[Transition],
        bindings: dict[str, dict],
    ) -> None:
        """Close an OCR chain on a model-free figure_entry fed best-first by whichever step ran."""
        terminal_id = f"{slot}_entry"
        nodes.append(ActionNodeBlob(id=terminal_id, family="enrich", kind="figure_entry"))
        # Every step, on success, closes the branch on the shared terminal.
        for step_id in frag.exits:
            transitions.append(
                Transition(from_node_id=step_id, to_node_id=terminal_id, condition=OnSuccess())
            )
        # The join reads whichever step produced — best-first, as computed by the fragment.
        bindings[terminal_id] = {"figure": frag.output}

    @classmethod
    def __close_vlm(
        cls,
        slot: str,
        frag: ChainFragment,
        nodes: list,
        transitions: list[Transition],
        bindings: dict[str, dict],
    ) -> None:
        """Close a VLM chain on a model-free vlm_entry fed best-first by whichever step described."""
        terminal_id = f"{slot}_entry"
        nodes.append(ActionNodeBlob(id=terminal_id, family="enrich", kind="vlm_entry"))
        # Every step, on success, closes the branch on the shared terminal.
        for step_id in frag.exits:
            transitions.append(
                Transition(from_node_id=step_id, to_node_id=terminal_id, condition=OnSuccess())
            )
        # The join reads the scored entry of whichever step produced — best-first, score dropped.
        bindings[terminal_id] = {"entry": frag.output}


__all__ = ["EnrichBodyBuilder"]
