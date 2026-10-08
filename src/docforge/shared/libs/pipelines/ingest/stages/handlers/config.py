# ====== Code Summary ======
# StageConfigHandler — compiles set_config onto a PipelineState: a composite intake sub-node, the
# convert card (stored under the intake ``convert`` node), the head step of a chain stage, or a stage's
# single config field. Every branch resolves the new config through StageConfigMerge against the
# node's CURRENT config (``replace`` stores the patch verbatim, ``merge`` overlays it, null deletes).

# ====== Local Project Imports ======
from ..config_merge import ConfigMode, StageConfigMerge
from ..models import SetStageConfig
from ..spec import StageKey
from ..state import ChainSpec, PipelineState
from .tables import CHAIN_STAGES, CONFIGS


class StageConfigHandler:
    """Static handler for the set_config action."""

    def __new__(cls, *args: object, **kwargs: object) -> None:
        raise TypeError("StageConfigHandler is a static-only class and cannot be instantiated.")

    @staticmethod
    def __set_chain_head(
        state: PipelineState, stage: str, config: dict, mode: ConfigMode, notices: list[str]
    ) -> None:
        """Edit a chain stage's head step (the selected provider); SetChain edits the fuller chain."""
        field, _ = CHAIN_STAGES[stage]
        chain: ChainSpec = getattr(state, field)
        if not chain.steps:
            notices.append(f"stage '{stage}' has no provider to configure")
            return
        head, *rest = chain.steps
        resolved = StageConfigMerge.resolve(head.config, config, mode)
        setattr(
            state,
            field,
            ChainSpec(
                family=chain.family,
                steps=[head.model_copy(update={"config": resolved}), *rest],
            ),
        )

    @staticmethod
    def __set_field(
        state: PipelineState, stage: str, config: dict, mode: ConfigMode, notices: list[str]
    ) -> None:
        """Edit a stage exposing a single config field (lifting enrich's topology selectors)."""
        field = CONFIGS.get(stage)
        if field is None:
            notices.append(f"stage '{stage}' has no editable config")
            return
        # The enrich config additionally carries the topology selectors — lift them onto the state so
        # the assembler picks the classifier-free uniform body (and its ocr/vlm treatment) when asked.
        # The values stay in classify_config too (valid FigureClassifyConfig fields) so classified
        # mode round-trips them through the classify node's own config.
        resolved = StageConfigMerge.resolve(getattr(state, field), config, mode)
        if stage == StageKey.ENRICH:
            enrich_mode = resolved.get("figure_enrich_mode", "classified")
            state.figure_enrich_mode = "uniform" if enrich_mode == "ocr_only" else enrich_mode
            state.uniform_treatment = resolved.get("uniform_treatment", "ocr")
        setattr(state, field, resolved)

    @classmethod
    def apply(cls, state: PipelineState, action: SetStageConfig, notices: list[str]) -> None:
        """
        Edit a stage's config (its primary node, or a named node of a composite stage).

        Args:
            state (PipelineState): The state to mutate.
            action (SetStageConfig): The action carrying stage, optional node, config and mode.
            notices (list[str]): Collector for no-op notices.
        """
        stage, node, config, mode = action.stage, action.node, action.config, action.mode
        # 1. Intake is composite — a named node targets one of its fixed sub-nodes.
        if stage == StageKey.INTAKE:
            if node is None:
                notices.append("intake config needs a node (e.g. 'convert')")
                return
            current = state.intake_configs.get(node)
            state.intake_configs[node] = StageConfigMerge.resolve(current, config, mode)
            return
        # 2. Convert is surfaced as its own stage card but its node lives in the intake segment, so
        #    its config is stored under the ``convert`` intake node id (node arg unused: primary).
        if stage == StageKey.CONVERT:
            current = state.intake_configs.get("convert")
            state.intake_configs["convert"] = StageConfigMerge.resolve(current, config, mode)
            return
        # 3. A chain stage (parse, embed) — editing its config edits the head step.
        if stage in CHAIN_STAGES:
            cls.__set_chain_head(state, stage, config, mode, notices)
            return
        # 4. Every other stage exposes a single config field.
        cls.__set_field(state, stage, config, mode, notices)


__all__ = ["StageConfigHandler"]
