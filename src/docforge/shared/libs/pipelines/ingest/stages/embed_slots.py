# ====== Code Summary ======
# EmbedSlots — the stage layer's face over the embed node's two independent provider SLOTS (dense,
# sparse). The view lists each slot (its provider or off, the kinds that can fill it, its config and
# each kind's form schema); the slot actions edit ``config[slot]`` of the embed chain HEAD in place:
# pick a slot provider (or switch the slot off), or edit the slot's config keeping its kind. The
# embedder itself stays one node so a dense + sparse pair on the same bge_server is ONE combined call.

# ====== Standard Library Imports ======
from typing import Any

# ====== Internal Project Imports ======
from shared_libs.pipelines.nodes.embed.dense_sparse import DENSE_SPARSE_KIND, IN_STACK_BGE_URL
from shared_libs.pipelines.nodes.embed.providers import EmbedAxis, EmbedProviderRegistry

# ====== Local Project Imports ======
from .config_merge import ConfigMode, StageConfigMerge
from .models import ProviderSlotView
from .state import ChainSpec, PipelineState

# Slot key → (title, description) of the embed node's provider slots, in display order.
_SLOTS: dict[str, tuple[str, str]] = {
    EmbedAxis.DENSE: (
        "Dense provider",
        "Semantic vectors (content + semantic metadata fields). Off = a sparse-only collection "
        "(no semantic search).",
    ),
    EmbedAxis.SPARSE: (
        "Sparse provider",
        "Lexical vectors (content + lexical metadata fields + the query). bge_server = learned "
        "weights; bm25_local = in-process BM25 scored with the store's IDF. Same bge_server endpoint "
        "as the dense slot → one combined call, made with the DENSE slot's api_key and "
        "retry/timeout policy (this slot's are then unused). Off = a dense-only collection.",
    ),
}

# The provider kind whose remote endpoint is pre-filled with the in-stack host on a fresh pick.
_IN_STACK_KIND = "bge_server"


class EmbedSlots:
    """Static view + mutations of the embed node's dense / sparse provider slots."""

    def __new__(cls, *args: object, **kwargs: object) -> None:
        raise TypeError("EmbedSlots is a static-only class and cannot be instantiated.")

    @staticmethod
    def is_slot(slot: str | None) -> bool:
        """Whether a key names one of the embed provider slots."""
        return slot in _SLOTS

    @staticmethod
    def __head_config(state: PipelineState) -> dict[str, Any] | None:
        """The head step's config when it is the slot node, else None."""
        steps = state.embed_chain.steps
        if not steps or steps[0].kind != DENSE_SPARSE_KIND:
            return None
        return steps[0].config

    @staticmethod
    def __set_head_config(state: PipelineState, config: dict[str, Any]) -> None:
        """Replace the head step's config (the rest of the chain untouched)."""
        head, *rest = state.embed_chain.steps
        state.embed_chain = ChainSpec(
            family=state.embed_chain.family,
            steps=[head.model_copy(update={"config": config}), *rest],
        )

    @classmethod
    def __slot_value(cls, config: dict[str, Any], slot: str) -> dict[str, Any] | None:
        """A slot's stored value — an omitted slot is the stock in-stack bge_server."""
        if slot not in config:
            return {"kind": _IN_STACK_KIND, "base_url": IN_STACK_BGE_URL}
        value = config[slot]
        return dict(value) if isinstance(value, dict) else None

    @classmethod
    def views(cls, state: PipelineState) -> list[ProviderSlotView]:
        """
        The slot views of the embed stage (empty when its head is not the slot node).

        Args:
            state (PipelineState): The canonical state.

        Returns:
            list[ProviderSlotView]: The dense then the sparse slot.
        """
        config = cls.__head_config(state)
        if config is None:
            return []
        views: list[ProviderSlotView] = []
        for slot, (title, description) in _SLOTS.items():
            value = cls.__slot_value(config, slot)
            views.append(
                ProviderSlotView(
                    slot=slot,
                    title=title,
                    description=description,
                    provider=value.get("kind") if value else None,
                    available=EmbedProviderRegistry.kinds(EmbedAxis(slot)),
                    config=value,
                    config_schemas=EmbedProviderRegistry.config_schemas(EmbedAxis(slot)),
                )
            )
        return views

    @classmethod
    def __fresh_slot(cls, config: dict[str, Any], slot: str, kind: str) -> dict[str, Any]:
        """A newly picked slot provider: its required fields filled build-safe.

        A remote bge_server reuses the OTHER slot's bge endpoint when there is one (so the pair
        becomes one combined call), else the in-stack host; other required strings start empty.
        """
        fresh: dict[str, Any] = {"kind": kind}
        for name, field in EmbedProviderRegistry.get(kind).Config.model_fields.items():
            if field.is_required() and name not in fresh:
                fresh[name] = ""
        if kind == _IN_STACK_KIND:
            other = cls.__slot_value(config, next(s for s in _SLOTS if s != slot))
            same_kind = other is not None and other.get("kind") == kind
            fresh["base_url"] = other["base_url"] if same_kind else IN_STACK_BGE_URL
        return fresh

    @classmethod
    def set_provider(
        cls, state: PipelineState, slot: str, kind: str | None, notices: list[str]
    ) -> None:
        """
        Pick a slot's provider (kind null = slot off); the same kind keeps its config + secret.

        Args:
            state (PipelineState): The state to mutate.
            slot (str): ``dense`` / ``sparse``.
            kind (str | None): The provider kind, or None to switch the slot off.
            notices (list[str]): Collector for refusals (the state is then unchanged).
        """
        config = cls.__head_config(state)
        if config is None:
            notices.append("the embed stage has no dense/sparse slot embedder")
            return
        current = cls.__slot_value(config, slot)
        other = cls.__slot_value(config, next(s for s in _SLOTS if s != slot))
        # 1. Off: refused when the other slot is off too (the embedder would index nothing).
        if kind is None:
            if other is None:
                notices.append(f"cannot turn the {slot} slot off — the other slot is off too")
                return
            cls.__set_head_config(state, {**config, slot: None})
            return
        # 2. A kind that cannot fill this slot is DATA (a notice), never a raise.
        if kind not in EmbedProviderRegistry.kinds(EmbedAxis(slot)):
            notices.append(
                f"'{kind}' is not a {slot} provider "
                f"(choose: {EmbedProviderRegistry.kinds(EmbedAxis(slot))})"
            )
            return
        # 3. Same kind → unchanged (keeps its endpoint and stored secret); else a fresh slot.
        if current is not None and current.get("kind") == kind:
            cls.__set_head_config(state, {**config, slot: current})
            return
        cls.__set_head_config(state, {**config, slot: cls.__fresh_slot(config, slot, kind)})

    @classmethod
    def set_config(
        cls,
        state: PipelineState,
        slot: str,
        patch: dict[str, Any],
        mode: ConfigMode,
        notices: list[str],
    ) -> None:
        """
        Edit a slot's provider config (replace / merge), keeping its provider kind.

        Args:
            state (PipelineState): The state to mutate.
            slot (str): ``dense`` / ``sparse``.
            patch (dict): The new slot config (replace) or the keys to change (merge).
            mode (ConfigMode): ``replace`` or ``merge`` (StageConfigMerge rules, endpoint-scoped
                secrets included).
            notices (list[str]): Collector for refusals.
        """
        config = cls.__head_config(state)
        if config is None:
            notices.append("the embed stage has no dense/sparse slot embedder")
            return
        current = cls.__slot_value(config, slot)
        if current is None:
            notices.append(f"the {slot} slot is off — pick its provider first (set_provider)")
            return
        resolved = StageConfigMerge.resolve(current, patch, mode)
        resolved["kind"] = current["kind"]
        cls.__set_head_config(state, {**config, slot: resolved})


__all__ = ["EmbedSlots"]
