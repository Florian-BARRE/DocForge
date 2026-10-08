# ====== Code Summary ======
# StageToggleHandler — compiles enable_stage / disable_stage onto a PipelineState: flips the stage's
# boolean, cascades its dependencies transitively (enabling enrich pulls render back, disabling render
# drops enrich) and restores build-safe stock defaults on re-enable.
#
# Disable/re-enable semantics (v1, deliberate — no side-channel config storage): disabling a stage
# REMOVES its nodes from the blob, so its config is gone from the only state carrier there is (the
# blob itself). Re-enabling therefore restores the stage's stock, build-safe DEFAULTS — it does not
# resurrect a previous edited config.

# ====== Local Project Imports ======
from ..models import DisableStage, EnableStage
from ..spec import StageKey, StageSpecs
from ..state import PipelineState, default_state
from .tables import TOGGLES


class StageToggleHandler:
    """Static handler for the enable/disable stage actions (with dependency cascades)."""

    def __new__(cls, *args: object, **kwargs: object) -> None:
        raise TypeError("StageToggleHandler is a static-only class and cannot be instantiated.")

    @classmethod
    def __toggle(cls, state: PipelineState, stage: str, on: bool, notices: list[str]) -> None:
        """Enable/disable a removable stage, cascading its dependencies."""
        # 1. Only removable, boolean-toggled stages can flip; the rest is a clean no-op notice that
        #    names the real toggleable keys (so e.g. "metagen" points at metagen_chunk/_document).
        if stage not in TOGGLES:
            notices.append(
                f"stage '{stage}' cannot be toggled — toggleable stages are: "
                f"{', '.join(sorted(TOGGLES))}."
            )
            return
        attr = TOGGLES[stage]
        if getattr(state, attr) == on:
            notices.append(f"stage '{stage}' is already {'enabled' if on else 'disabled'}")
        setattr(state, attr, on)

        # 2. A stage removed from the blob lost its config — restore build-safe defaults on the
        #    way back so the re-enabled node always builds and is usefully pre-filled.
        if on:
            cls.__restore_defaults(state, stage)
            cls.__cascade_enable(state, stage, notices)
        else:
            cls.__cascade_disable(state, stage, notices)

    @classmethod
    def __cascade_enable(cls, state: PipelineState, stage: str, notices: list[str]) -> None:
        """Enabling a stage enables the stages it requires — transitively (to a fixpoint)."""
        for required in StageSpecs.meta(stage).requires:
            if required in TOGGLES and not getattr(state, TOGGLES[required]):
                setattr(state, TOGGLES[required], True)
                cls.__restore_defaults(state, required)
                notices.append(f"enabled '{required}' because '{stage}' depends on it")
                # Recurse so a required stage's OWN requirements are pulled in too (requires is a DAG).
                cls.__cascade_enable(state, required, notices)

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

    @classmethod
    def __cascade_disable(cls, state: PipelineState, stage: str, notices: list[str]) -> None:
        """Disabling a stage disables the stages that require it — transitively (to a fixpoint)."""
        for meta in StageSpecs.ORDER:
            if stage in meta.requires and meta.key in TOGGLES and getattr(state, TOGGLES[meta.key]):
                setattr(state, TOGGLES[meta.key], False)
                notices.append(f"disabled '{meta.key}' because it depends on '{stage}'")
                # Recurse so a dependent's OWN dependents are disabled too (no orphaned enabled node).
                cls.__cascade_disable(state, meta.key, notices)

    @classmethod
    def enable(cls, state: PipelineState, action: EnableStage, notices: list[str]) -> None:
        """
        Compile an ``enable_stage`` action (mutating ``state`` in place).

        Args:
            state (PipelineState): The state to mutate.
            action (EnableStage): The action naming the stage to enable.
            notices (list[str]): Collector for cascade / no-op notices.
        """
        cls.__toggle(state, action.stage, True, notices)

    @classmethod
    def disable(cls, state: PipelineState, action: DisableStage, notices: list[str]) -> None:
        """
        Compile a ``disable_stage`` action (mutating ``state`` in place).

        Args:
            state (PipelineState): The state to mutate.
            action (DisableStage): The action naming the stage to disable.
            notices (list[str]): Collector for cascade / no-op notices.
        """
        cls.__toggle(state, action.stage, False, notices)


__all__ = ["StageToggleHandler"]
