# ====== Code Summary ======
# StageViewer — turns a PipelineState into the StageCatalog the UI renders: the FULL ordered
# skeleton, every canonical stage present (disabled ones with enabled=False so the rail shows the
# whole chain, greyed where off). Per stage it fills the interaction face from the spec, the current
# provider/config from the state, the enrich model chains (one ChainView per figure-class site, each
# flagged with its family so the UI colours them apart) and the contextualize method stack. The
# available kinds come from the live registry, so a new provider folder shows up with zero edits.

# ====== Third-Party Library Imports ======
from loggerplusplus import loggerplusplus

# ====== Internal Project Imports ======
from shared_libs.pipelines.registry import NodeRegistry

# ====== Local Project Imports ======
from .models import ChainView, StageCatalog, StageView
from .spec import StageKey, StageSpecs
from .state import PipelineState


class StageViewer:
    """Static viewer building the product-level StageCatalog from a PipelineState."""

    logger = loggerplusplus.bind(identifier="StageViewer")

    def __new__(cls, *args: object, **kwargs: object) -> None:
        raise TypeError("StageViewer is a static-only class and cannot be instantiated.")

    @classmethod
    def catalog(cls, state: PipelineState) -> StageCatalog:
        """
        Build the full stage catalog for a pipeline state.

        Args:
            state (PipelineState): The canonical state to view.

        Returns:
            StageCatalog: The ordered skeleton, disabled stages included.
        """
        return StageCatalog(stages=[cls.__stage(meta, state) for meta in StageSpecs.ORDER])

    @classmethod
    def __stage(cls, meta, state: PipelineState) -> StageView:
        """Build one stage's view from its spec and the current state."""
        enabled = cls.__enabled(meta.key, state)
        provider, available = cls.__provider(meta, state)
        return StageView(
            key=meta.key, title=meta.title, description=meta.description, kind=meta.kind,
            enabled=enabled, removable=meta.removable, family=meta.family,
            provider=provider, available=available,
            config=cls.__config(meta.key, state),
            chains=cls.__chains(meta.key, state),
            stack=list(state.stack) if meta.key == StageKey.CONTEXTUALIZE else [],
            requires=list(meta.requires),
            notes=cls.__notes(meta, state, enabled),
        )

    @classmethod
    def __enabled(cls, key: str, state: PipelineState) -> bool:
        """Whether a stage is currently part of the pipeline."""
        return {
            StageKey.RENDER: state.render_on,
            StageKey.ENRICH: state.enrich_on,
            StageKey.CONTEXTUALIZE: bool(state.stack),
            StageKey.METAGEN_CHUNK: state.metachunk_on,
            StageKey.METAGEN_DOCUMENT: state.metadoc_on,
            StageKey.EMBED: state.embed_on,
        }.get(key, True)

    @classmethod
    def __provider(cls, meta, state: PipelineState) -> tuple[str | None, list[str]]:
        """The selected kind + the family's available kinds (provider stages only)."""
        if meta.kind != "provider":
            return None, []
        selected = {
            StageKey.PARSE: state.parser_kind,
            StageKey.CHUNK: state.chunker_kind,
            StageKey.EMBED: state.embed_kind,
        }.get(meta.key)
        return selected, NodeRegistry.kinds(meta.family) if meta.family else []

    @classmethod
    def __config(cls, key: str, state: PipelineState) -> dict | None:
        """The single editable config a stage exposes (None for composite/stack stages)."""
        return {
            StageKey.PARSE: state.parser_config,
            StageKey.RENDER: state.render_config,
            StageKey.ENRICH: state.classify_config,
            StageKey.CHUNK: state.chunker_config,
            StageKey.METAGEN_CHUNK: state.metachunk_config,
            StageKey.METAGEN_DOCUMENT: state.metadoc_config,
            StageKey.EMBED: state.embed_config,
        }.get(key)

    @classmethod
    def __chains(cls, key: str, state: PipelineState) -> list[ChainView]:
        """The per-class model chains of the enrich stage (empty elsewhere)."""
        if key != StageKey.ENRICH:
            return []
        views: list[ChainView] = []
        for branch in StageSpecs.FIGURE_BRANCHES:
            spec = state.chains.get(branch.slot)
            views.append(ChainView(
                slot=branch.slot, title=branch.title, description=branch.description,
                family=branch.family, available=NodeRegistry.kinds(branch.family),
                steps=list(spec.steps) if spec else [],
            ))
        return views

    @classmethod
    def __notes(cls, meta, state: PipelineState, enabled: bool) -> str | None:
        """A short caveat surfaced to the user for the stages that warrant one."""
        if meta.key == StageKey.ENRICH and enabled and not state.render_on:
            return "Enrichment needs the render stage to embed figure crops — enable it."
        # A disabled removable stage is off the pipeline; re-enabling starts from defaults.
        if meta.removable and not enabled:
            note = "Disabled — re-enabling restores this stage's default configuration."
            if meta.key == StageKey.EMBED:
                return f"{note} No vectors are indexed while off."
            return note
        return None


__all__ = ["StageViewer"]
