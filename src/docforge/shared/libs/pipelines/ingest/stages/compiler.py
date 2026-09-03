# ====== Code Summary ======
# StageCompiler — compiles a stage-level ACTION into a blob transformation. It reads the blob into a
# PipelineState, mutates that state (toggling with dependency cascades, swapping a provider,
# rebuilding a chain or the contextualize stack), then re-assembles the blob — so the result is
# ALWAYS buildable and correctly wired (the rebindings live in the assembler's spines, not here).
# This is the "no doubt, coherent end to end" contract: disabling render cascades to enrich, enabling
# enrich pulls render back, and every downstream consumer follows automatically. A nonsensical action
# (unknown stage, a toggle on a fixed stage) is DATA — a notice is emitted and the blob is unchanged,
# never an exception.
#
# Disable/re-enable semantics (v1, deliberate — no side-channel config storage): disabling a stage
# REMOVES its nodes from the blob, so its config is gone from the only state carrier there is (the
# blob itself). Re-enabling therefore restores the stage's stock, build-safe DEFAULTS — it does not
# resurrect a previous edited config. The stage view flags this on every disabled removable stage so
# the UI can warn before a toggle-off discards edits.

# ====== Third-Party Library Imports ======
from loggerplusplus import LoggerClass

# ====== Internal Project Imports ======
from shared_libs.pipelines.build.blob import GroupNodeBlob
from shared_libs.pipelines.registry import NodeRegistry

# ====== Local Project Imports ======
from .assembler import IngestAssembler
from .chain_rules import ChainRules
from .models import (
    ChainStep,
    DisableStage,
    EnableStage,
    SetChain,
    SetProvider,
    SetStack,
    SetStageConfig,
    StackMethod,
    StageAction,
)
from .reader import StateReader
from .spec import StageKey, StageSpecs
from .state import ChainSpec, PipelineState, default_state

# Stage key → the PipelineState boolean that toggles it.
_TOGGLES = {
    StageKey.RENDER: "render_on",
    StageKey.ENRICH: "enrich_on",
    StageKey.METAGEN_CHUNK: "metachunk_on",
    StageKey.METAGEN_DOCUMENT: "metadoc_on",
    StageKey.EMBED: "embed_on",
}

# Stage key → (state field for the provider kind, state field for its config). Parse and embed are
# NOT here: they are fallback chains, so SetProvider is sugar for a 1-step chain (see __set_provider).
_PROVIDERS = {
    StageKey.CHUNK: ("chunker_kind", "chunker_config"),
}

# Chain-capable linear stages → (state field holding the ChainSpec, the registry family). These are
# provider stages whose provider is a fallback chain, edited with a slot-less SetChain. Parse is
# scored (ScoreBelow escalation); embed is not (failure-only) — the family's scored flag decides.
_CHAIN_STAGES = {
    StageKey.PARSE: ("parse_chain", "parser"),
    StageKey.EMBED: ("embed_chain", "embed"),
}

# Metagen chains → (state field holding the structgen ChainSpec, the family). Unlike _CHAIN_STAGES
# these are NOT provider stages: metagen is a TOGGLE whose editable config is the PREP endpoint
# (_CONFIGS), while its model ladder is a slot-less SetChain over the structgen family (non-scored,
# so score thresholds are dropped). Kept apart so set_config keeps hitting the prep config, and only
# set_chain reaches the ladder.
_METAGEN_CHAINS = {
    StageKey.METAGEN_CHUNK: ("metachunk_chain", "structgen"),
    StageKey.METAGEN_DOCUMENT: ("metadoc_chain", "structgen"),
}

# Stage key → the state config field its primary node exposes (chain stages edit their chain head).
_CONFIGS = {
    StageKey.RENDER: "render_config",
    StageKey.ENRICH: "classify_config",
    StageKey.CHUNK: "chunker_config",
    StageKey.METAGEN_CHUNK: "metachunk_config",
    StageKey.METAGEN_DOCUMENT: "metadoc_config",
}


class StageCompiler(LoggerClass):
    """Compiles a stage action into a blob transformation (parse → mutate state → assemble)."""

    def __init__(self) -> None:
        LoggerClass.__init__(self)

    def apply(self, blob: GroupNodeBlob, action: StageAction) -> tuple[GroupNodeBlob, list[str]]:
        """
        Apply a stage action to a blob, returning the recompiled blob and any notices.

        Args:
            blob (GroupNodeBlob): The blob the action starts from (never mutated).
            action (StageAction): The stage-level action to compile.

        Returns:
            tuple[GroupNodeBlob, list[str]]: The recompiled blob and the notices raised while
            compiling (dependency cascades, ignored no-ops).
        """
        # 1. Read the blob into the canonical state; mutate a copy per the action.
        state = StateReader.read(blob)
        notices: list[str] = []
        self.__dispatch(state, action, notices)

        # 2. Re-assemble — the spines rewire every consumer to the nearest enabled producer.
        rebuilt = IngestAssembler.assemble(state)
        # 3. Warn while it is still cheap: an ENABLED provider node still pointed at a template
        #    placeholder (unreachable host / SET_ME key) builds fine but fails at the first spend
        #    (or at preflight). Surface it now, at edit time, so the user wires a real endpoint
        #    before ingesting rather than discovering it from a failed job.
        self.__warn_placeholders(rebuilt, notices)
        self.logger.info(f"compiled stage action '{action.action}' ({len(notices)} notice(s))")
        return rebuilt, notices

    # The template's pre-filled but non-executable endpoints — a stage shipping OFF carries these
    # until the user opts in and sets a real one; enabled while still holding one is worth flagging.
    _PLACEHOLDER_MARKERS = ("vlm:8000", "llm:8000", "SET_ME")

    @classmethod
    def __warn_placeholders(cls, blob: GroupNodeBlob, notices: list[str]) -> None:
        """Append one notice per enabled action node with a placeholder or missing endpoint/key."""
        flagged: set[str] = set()
        for node_id, config in cls.__action_configs(blob):
            if node_id in flagged:
                continue
            notice = cls.__endpoint_notice(node_id, config)
            if notice is not None:
                flagged.add(node_id)
                notices.append(notice)

    @classmethod
    def __endpoint_notice(cls, node_id: str, config: object) -> str | None:
        """The edit-time endpoint caveat for one enabled action node, or ``None`` when it is sound.

        The assembled blob holds only ENABLED stages' nodes, so every node reached here is live.
        A missing endpoint (or a template placeholder) builds cleanly — GraphValidator is structural
        only — and would otherwise fail at the first spend (or at preflight). Surfacing it here, at
        edit time, lets the user wire a real endpoint before ingesting rather than discovering it
        from a failed job.

        Args:
            node_id (str): The node whose config is inspected (named in the notice).
            config (object): The node's config dict (any non-dict is treated as endpoint-free).

        Returns:
            str | None: The caveat to surface, or ``None`` when the node needs none.
        """
        # 0. A fully-local classify backend needs no endpoint at all — never flag its empty base_url
        #    (it classifies offline via RapidOCR, so there is nothing to preflight).
        if isinstance(config, dict) and config.get("classify_backend") == "local":
            return None
        # 1. A template placeholder endpoint/key — a stage shipping OFF carries these until opt-in.
        if any(marker in repr(config) for marker in cls._PLACEHOLDER_MARKERS):
            return (
                f"node '{node_id}' still points at a template placeholder endpoint/key — set a "
                f"reachable URL and credentials before ingesting, or the run fails at preflight."
            )
        if not isinstance(config, dict):
            return None
        # 2. A network node with no endpoint at all — an empty base_url is never legitimate (an
        #    in-stack service still has a concrete host), so flag it whatever the node kind.
        base_url = config.get("base_url")
        if isinstance(base_url, str) and not base_url.strip():
            return (
                f"node '{node_id}' has no endpoint set (base_url is empty) — set a reachable URL "
                f"before ingesting, or the run fails at preflight."
            )
        # 3. A HOSTED endpoint (https) with an empty api_key — an in-stack http service legitimately
        #    needs no key, so the key is only flagged when the endpoint is a remote https one.
        api_key = config.get("api_key")
        if (
            isinstance(base_url, str)
            and base_url.strip().lower().startswith("https://")
            and isinstance(api_key, str)
            and not api_key.strip()
        ):
            return (
                f"node '{node_id}' points at a hosted endpoint with no api_key — set the credential "
                f"before ingesting, or the run fails at preflight."
            )
        return None

    @classmethod
    def __action_configs(cls, blob: GroupNodeBlob):
        """Every action node's (id, config) in the graph, recursing ForEach bodies + sub-groups."""
        for node in blob.nodes:
            body = getattr(node, "body", None)  # ForEach body
            if body is not None:
                yield from cls.__action_configs(body)
            nested = getattr(node, "nodes", None)  # a nested Group exposes children under .nodes
            if nested is not None:
                yield from cls.__action_configs(node)
            config = getattr(node, "config", None)
            if config is not None:
                yield node.id, config

    def __dispatch(self, state: PipelineState, action: StageAction, notices: list[str]) -> None:
        """Route an action to its handler (mutating ``state`` in place)."""
        match action:
            case EnableStage():
                self.__toggle(state, action.stage, True, notices)
            case DisableStage():
                self.__toggle(state, action.stage, False, notices)
            case SetProvider():
                self.__set_provider(state, action.stage, action.kind, notices)
            case SetStageConfig():
                self.__set_config(state, action.stage, action.node, action.config, notices)
            case SetChain():
                self.__set_chain(state, action.stage, action.slot, action.steps, notices)
            case SetStack():
                self.__set_stack(state, action.stage, action.steps, notices)

    def __toggle(self, state: PipelineState, stage: str, on: bool, notices: list[str]) -> None:
        """Enable/disable a removable stage, cascading its dependencies."""
        # 1. Only removable, boolean-toggled stages can flip; the rest is a clean no-op notice that
        #    names the real toggleable keys (so e.g. "metagen" points at metagen_chunk/_document).
        if stage not in _TOGGLES:
            notices.append(
                f"stage '{stage}' cannot be toggled — toggleable stages are: "
                f"{', '.join(sorted(_TOGGLES))}."
            )
            return
        attr = _TOGGLES[stage]
        if getattr(state, attr) == on:
            notices.append(f"stage '{stage}' is already {'enabled' if on else 'disabled'}")
        setattr(state, attr, on)

        # 2. A stage removed from the blob lost its config — restore build-safe defaults on the
        #    way back so the re-enabled node always builds and is usefully pre-filled.
        if on:
            self.__restore_defaults(state, stage)
            self.__cascade_enable(state, stage, notices)
        else:
            self.__cascade_disable(state, stage, notices)

    def __cascade_enable(self, state: PipelineState, stage: str, notices: list[str]) -> None:
        """Enabling a stage enables the stages it requires — transitively (to a fixpoint)."""
        for required in StageSpecs.meta(stage).requires:
            if required in _TOGGLES and not getattr(state, _TOGGLES[required]):
                setattr(state, _TOGGLES[required], True)
                self.__restore_defaults(state, required)
                notices.append(f"enabled '{required}' because '{stage}' depends on it")
                # Recurse so a required stage's OWN requirements are pulled in too (requires is a DAG).
                self.__cascade_enable(state, required, notices)

    @staticmethod
    def __restore_defaults(state: PipelineState, stage: str) -> None:
        """Fill a just-re-enabled stage's empty config/chains from the stock defaults."""
        stock = default_state()
        if stage == StageKey.RENDER and not state.render_config:
            state.render_config = dict(stock.render_config)
        elif stage == StageKey.ENRICH:
            if not state.classify_config:
                state.classify_config = dict(stock.classify_config)
            if not state.chains:
                state.chains = {
                    slot: spec.model_copy(deep=True) for slot, spec in stock.chains.items()
                }
        elif stage == StageKey.METAGEN_CHUNK:
            if not state.metachunk_config:
                state.metachunk_config = dict(stock.metachunk_config)
            if not state.metachunk_chain.steps:
                state.metachunk_chain = stock.metachunk_chain.model_copy(deep=True)
        elif stage == StageKey.METAGEN_DOCUMENT:
            if not state.metadoc_config:
                state.metadoc_config = dict(stock.metadoc_config)
            if not state.metadoc_chain.steps:
                state.metadoc_chain = stock.metadoc_chain.model_copy(deep=True)
        elif stage == StageKey.EMBED and not state.embed_chain.steps[0].config:
            # Re-enabling embed restores the stock 1-step chain (its config was gone with the node).
            state.embed_chain = stock.embed_chain

    def __cascade_disable(self, state: PipelineState, stage: str, notices: list[str]) -> None:
        """Disabling a stage disables the stages that require it — transitively (to a fixpoint)."""
        for meta in StageSpecs.ORDER:
            if (
                stage in meta.requires
                and meta.key in _TOGGLES
                and getattr(state, _TOGGLES[meta.key])
            ):
                setattr(state, _TOGGLES[meta.key], False)
                notices.append(f"disabled '{meta.key}' because it depends on '{stage}'")
                # Recurse so a dependent's OWN dependents are disabled too (no orphaned enabled node).
                self.__cascade_disable(state, meta.key, notices)

    def __set_provider(
        self, state: PipelineState, stage: str, kind: str, notices: list[str]
    ) -> None:
        """Swap an exclusive stage's kind and reset its config to build-safe schema defaults."""
        meta = StageSpecs.meta(stage) if stage in {*_PROVIDERS, *_CHAIN_STAGES} else None
        # 1. A chain-capable provider stage (parse): picking a provider is sugar for a 1-step chain.
        if stage in _CHAIN_STAGES:
            self.__set_stage_chain(state, stage, [ChainStep(kind=kind)], notices)
            return
        # 2. A single-provider stage (chunk, embed): swap the kind, reset its config.
        if meta is None:
            notices.append(f"stage '{stage}' has no provider to set")
            return
        if kind not in NodeRegistry.kinds(meta.family or ""):
            notices.append(f"'{kind}' is not a '{meta.family}' provider")
            return
        kind_field, config_field = _PROVIDERS[stage]
        setattr(state, kind_field, kind)
        setattr(state, config_field, ChainRules.reset_config(meta.family or "", kind))

    def __set_config(
        self, state: PipelineState, stage: str, node: str | None, config: dict, notices: list[str]
    ) -> None:
        """Replace a stage's config (its primary node, or a named node of a composite stage)."""
        # 1. Intake is composite — a named node targets one of its fixed sub-nodes.
        if stage == StageKey.INTAKE:
            if node is None:
                notices.append("intake config needs a node (e.g. 'convert')")
                return
            state.intake_configs[node] = dict(config)
            return
        # 2. A chain stage (parse, embed) — editing its config edits the head step (the selected
        #    provider); the fuller chain is edited with SetChain.
        if stage in _CHAIN_STAGES:
            field, _ = _CHAIN_STAGES[stage]
            chain: ChainSpec = getattr(state, field)
            if not chain.steps:
                notices.append(f"stage '{stage}' has no provider to configure")
                return
            head, *rest = chain.steps
            setattr(
                state,
                field,
                ChainSpec(
                    family=chain.family,
                    steps=[head.model_copy(update={"config": dict(config)}), *rest],
                ),
            )
            return
        # 3. Every other stage exposes a single config field.
        field = _CONFIGS.get(stage)
        if field is None:
            notices.append(f"stage '{stage}' has no editable config")
            return
        # 3b. The enrich config additionally carries the topology selector — lift it onto the state
        #     so the assembler picks the classifier-free ocr_only body when asked. The value stays in
        #     classify_config too (it is a valid FigureClassifyConfig field) so classified mode
        #     round-trips it through the classify node's own config.
        if stage == StageKey.ENRICH:
            state.figure_enrich_mode = config.get("figure_enrich_mode", "classified")
        setattr(state, field, dict(config))

    def __set_chain(
        self, state: PipelineState, stage: str, slot: str | None, steps: list, notices: list[str]
    ) -> None:
        """Rebuild a fallback chain — an enrich per-figure site (slot), or the stage itself (no slot)."""
        # A slot names an enrich per-figure model-call site; no slot means the stage IS the chain.
        if slot is None:
            self.__set_stage_chain(state, stage, steps, notices)
            return
        self.__set_enrich_chain(state, stage, slot, steps, notices)

    def __set_enrich_chain(
        self, state: PipelineState, stage: str, slot: str, steps: list, notices: list[str]
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
        completed = ChainRules.complete_steps(branch.family, steps)
        state.chains[slot] = ChainSpec(family=branch.family, steps=completed)
        if not steps:
            notices.append(f"chain '{slot}' emptied — figures of this class will be skipped")

    def __set_stage_chain(
        self, state: PipelineState, stage: str, steps: list, notices: list[str]
    ) -> None:
        """Rebuild a slot-less stage chain — a chain-capable linear stage (parse) or a metagen ladder."""
        mapping = (
            _CHAIN_STAGES
            if stage in _CHAIN_STAGES
            else (_METAGEN_CHAINS if stage in _METAGEN_CHAINS else None)
        )
        if mapping is None:
            notices.append(f"stage '{stage}' has no chain to set")
            return
        field, family = mapping[stage]
        self.__rebuild_stage_chain(state, stage, field, family, steps, notices)

    def __rebuild_stage_chain(
        self,
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
        # 2. Apply the shared family chain rules; an unknown kind leaves the chain unchanged.
        completed, chain_notices = ChainRules.resolve(family, steps)
        notices.extend(chain_notices)
        if completed is None:
            return
        setattr(state, field, ChainSpec(family=family, steps=completed))

    def __set_stack(
        self, state: PipelineState, stage: str, steps: list, notices: list[str]
    ) -> None:
        """Rebuild the ordered contextualize stack (empty disables the stage).

        Each method's config is completed build-safe (the llm method's config edits its PREP node).
        The llm method additionally carries a generic-llm chain, resolved through the shared chain
        rules (build-safe steps, non-scored so any score threshold is dropped, single-use guards).
        """
        if stage != StageKey.CONTEXTUALIZE:
            notices.append(f"stage '{stage}' has no stack to set")
            return
        # An unknown method kind is DATA, not an exception — completing its config would call
        # NodeRegistry.get and RAISE, so leave the stack unchanged with a notice (as every sibling
        # chain/provider edit does; this is the one path the P3 guard had missed).
        available = set(NodeRegistry.kinds("contextualize"))
        unknown = [step.kind for step in steps if step.kind not in available]
        if unknown:
            notices.extend(f"'{kind}' is not a 'contextualize' method" for kind in unknown)
            return
        resolved: list = []
        for step in steps:
            method = step.model_copy(
                update={
                    "config": {**ChainRules.reset_config("contextualize", step.kind), **step.config}
                }
            )
            if step.kind == "llm":
                method = self.__resolve_llm_chain(method, notices)
            resolved.append(method)
        state.stack = resolved
        if not steps:
            notices.append("contextualize stack emptied — chunks carry no added context")

    @staticmethod
    def __resolve_llm_chain(method: StackMethod, notices: list[str]) -> StackMethod:
        """Apply the generic-llm family chain rules to an llm method's chain (non-scored, failure-only).

        An unknown step kind is DATA — the chain is left as proposed with a notice (completing it
        would raise). Otherwise the steps are completed build-safe, any score threshold is stripped
        (llm is non-scored) and single-use repeats are flagged before the build rejects them.
        """
        chain = method.chain or ChainSpec(family="llm", steps=[ChainStep(kind="openai_compatible")])
        chain_steps = chain.steps or [ChainStep(kind="openai_compatible")]
        completed, chain_notices = ChainRules.resolve("llm", chain_steps)
        notices.extend(chain_notices)
        # An unknown kind (completed is None) keeps the proposed steps as-is; else the completed ones.
        steps = chain_steps if completed is None else completed
        return method.model_copy(update={"chain": ChainSpec(family="llm", steps=steps)})


__all__ = ["StageCompiler"]
