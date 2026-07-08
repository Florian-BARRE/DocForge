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

# Stage key → (state field for the provider kind, state field for its config). Parse is NOT here:
# it is a scored chain, so SetProvider(parse) is sugar for a 1-step chain (see __set_provider).
_PROVIDERS = {
    StageKey.CHUNK: ("chunker_kind", "chunker_config"),
    StageKey.EMBED: ("embed_kind", "embed_config"),
}

# Chain-capable linear stages → (state field holding the ChainSpec, the registry family). These are
# provider stages whose provider is a scored fallback chain, edited with a slot-less SetChain.
_CHAIN_STAGES = {
    StageKey.PARSE: ("parse_chain", "parser"),
}

# Stage key → the state config field its primary node exposes (parse edits its chain head directly).
_CONFIGS = {
    StageKey.RENDER: "render_config",
    StageKey.ENRICH: "classify_config",
    StageKey.CHUNK: "chunker_config",
    StageKey.METAGEN_CHUNK: "metachunk_config",
    StageKey.METAGEN_DOCUMENT: "metadoc_config",
    StageKey.EMBED: "embed_config",
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
        self.logger.info(f"compiled stage action '{action.action}' ({len(notices)} notice(s))")
        return rebuilt, notices

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
        # 1. Only removable, boolean-toggled stages can flip; the rest is a clean no-op notice.
        if stage not in _TOGGLES:
            notices.append(f"stage '{stage}' cannot be toggled (it is fixed or edited differently)")
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
        """Enabling a stage enables the stages it requires."""
        for required in StageSpecs.meta(stage).requires:
            if required in _TOGGLES and not getattr(state, _TOGGLES[required]):
                setattr(state, _TOGGLES[required], True)
                self.__restore_defaults(state, required)
                notices.append(f"enabled '{required}' because '{stage}' depends on it")

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
                state.chains = {slot: spec.model_copy(deep=True) for slot, spec in stock.chains.items()}
        elif stage == StageKey.METAGEN_CHUNK and not state.metachunk_config:
            state.metachunk_config = dict(stock.metachunk_config)
        elif stage == StageKey.METAGEN_DOCUMENT and not state.metadoc_config:
            state.metadoc_config = dict(stock.metadoc_config)
        elif stage == StageKey.EMBED and not state.embed_config:
            state.embed_config = dict(stock.embed_config)

    def __cascade_disable(self, state: PipelineState, stage: str, notices: list[str]) -> None:
        """Disabling a stage disables the stages that require it."""
        for meta in StageSpecs.ORDER:
            if stage in meta.requires and meta.key in _TOGGLES and getattr(state, _TOGGLES[meta.key]):
                setattr(state, _TOGGLES[meta.key], False)
                notices.append(f"disabled '{meta.key}' because it depends on '{stage}'")

    def __set_provider(self, state: PipelineState, stage: str, kind: str, notices: list[str]) -> None:
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
        # 2. Parse is a chain — editing its config edits the head step (the selected parser).
        if stage == StageKey.PARSE:
            head, *rest = state.parse_chain.steps
            state.parse_chain = ChainSpec(
                family=state.parse_chain.family,
                steps=[head.model_copy(update={"config": dict(config)}), *rest],
            )
            return
        # 3. Every other stage exposes a single config field.
        field = _CONFIGS.get(stage)
        if field is None:
            notices.append(f"stage '{stage}' has no editable config")
            return
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
        """Rebuild a chain-capable linear stage's own scored chain (parse today)."""
        if stage not in _CHAIN_STAGES:
            notices.append(f"stage '{stage}' has no chain to set")
            return
        field, family = _CHAIN_STAGES[stage]
        # 1. A required, non-removable stage must keep at least one provider — an empty chain would
        #    leave the pipeline without that step, so keep the current chain and warn.
        if not steps:
            notices.append(f"stage '{stage}' needs at least one provider — kept the current chain")
            return
        # 2. An unknown step kind is DATA, not an exception — leave the chain unchanged with a notice.
        unknown = ChainRules.unknown_kind_notices(family, steps)
        if unknown:
            notices.extend(unknown)
            return
        # 3. Complete each step's config build-safe, then apply the family-level chain rules.
        completed = ChainRules.complete_steps(family, steps)
        completed, threshold_notice = ChainRules.drop_unscored_thresholds(family, completed)
        if threshold_notice:
            notices.append(threshold_notice)
        notices.extend(ChainRules.duplicate_unique_notices(family, completed))
        setattr(state, field, ChainSpec(family=family, steps=completed))

    def __set_stack(
        self, state: PipelineState, stage: str, steps: list, notices: list[str]
    ) -> None:
        """Rebuild the ordered contextualize stack (empty disables the stage)."""
        if stage != StageKey.CONTEXTUALIZE:
            notices.append(f"stage '{stage}' has no stack to set")
            return
        state.stack = [
            step.model_copy(
                update={"config": {**ChainRules.reset_config("contextualize", step.kind), **step.config}}
            )
            for step in steps
        ]
        if not steps:
            notices.append("contextualize stack emptied — chunks carry no added context")


__all__ = ["StageCompiler"]
