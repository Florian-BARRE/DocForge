# ====== Code Summary ======
# StageCompiler — compiles a stage-level ACTION into a blob transformation. It reads the blob into a
# PipelineState, dispatches the action to its handler (handlers/: toggle with dependency cascades,
# provider swap, config edit, chain rebuild, contextualize stack), then re-assembles the blob — so the
# result is ALWAYS buildable and correctly wired (the rebindings live in the assembler's spines, not
# here). This is the "no doubt, coherent end to end" contract: disabling render cascades to enrich,
# enabling enrich pulls render back, and every downstream consumer follows automatically. A
# nonsensical action (unknown stage, a toggle on a fixed stage) is DATA — a notice is emitted and the
# blob is unchanged, never an exception.
#
# Disable/re-enable semantics (v1, deliberate — no side-channel config storage): disabling a stage
# REMOVES its nodes from the blob, so its config is gone from the only state carrier there is (the
# blob itself). Re-enabling therefore restores the stage's stock, build-safe DEFAULTS — it does not
# resurrect a previous edited config. The stage view flags this on every disabled removable stage so
# the UI can warn before a toggle-off discards edits.

# ====== Standard Library Imports ======
from collections.abc import Callable

# ====== Third-Party Library Imports ======
from loggerplusplus import LoggerClass

# ====== Internal Project Imports ======
from shared_libs.pipelines.build.blob import GroupNodeBlob

# ====== Local Project Imports ======
from .assembler import IngestAssembler
from .handlers import (
    PlaceholderEndpointNotices,
    StageChainHandler,
    StageConfigHandler,
    StageProviderHandler,
    StageStackHandler,
    StageToggleHandler,
)
from .models import (
    DisableStage,
    EnableStage,
    SetChain,
    SetProvider,
    SetStack,
    SetStageConfig,
    StageAction,
)
from .reader import StateReader
from .state import PipelineState

# An action handler mutates the state in place and appends its notices.
ActionHandler = Callable[[PipelineState, StageAction, list[str]], None]


class StageCompiler(LoggerClass):
    """Compiles a stage action into a blob transformation (parse → mutate state → assemble)."""

    # Action model → its handler. An action type absent here is a no-op (the blob reassembles as-is).
    __HANDLERS: dict[type, ActionHandler] = {
        EnableStage: StageToggleHandler.enable,
        DisableStage: StageToggleHandler.disable,
        SetProvider: StageProviderHandler.apply,
        SetStageConfig: StageConfigHandler.apply,
        SetChain: StageChainHandler.apply,
        SetStack: StageStackHandler.apply,
    }

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
        # 1. Read the blob into the canonical state; mutate it per the action via its handler.
        state = StateReader.read(blob)
        notices: list[str] = []
        handler = self.__HANDLERS.get(type(action))
        if handler is not None:
            handler(state, action, notices)

        # 2. Re-assemble — the spines rewire every consumer to the nearest enabled producer.
        rebuilt = IngestAssembler.assemble(state)
        # 3. Warn while it is still cheap: an ENABLED provider node still pointed at a template
        #    placeholder (unreachable host / SET_ME key) builds fine but fails at the first spend
        #    (or at preflight). Surface it now, at edit time, so the user wires a real endpoint
        #    before ingesting rather than discovering it from a failed job.
        PlaceholderEndpointNotices.warn(rebuilt, notices)
        self.logger.info(f"compiled stage action '{action.action}' ({len(notices)} notice(s))")
        return rebuilt, notices


__all__ = ["StageCompiler"]
