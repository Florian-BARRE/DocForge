# ====== Code Summary ======
# CostPlanExtractor — the pure bridge from a PipelineState (the collection's ACTUAL pipeline config)
# to a neutral CostPlan: which cost-incurring stages are ON, the provider kind and priced model of
# each, and the count of generated metadata fields (from the contract) that metagen fans out over.
# It reads only the state model and the passed-in field counts — no DB, no engine build — so the
# estimator that consumes the plan stays a pure function of config + sampled stats.

# ====== Standard Library Imports ======
from dataclasses import dataclass

# ====== Local Project Imports ======
from ..stages.state import PipelineState
from .rates import LOCAL_FREE_KINDS


@dataclass(frozen=True, slots=True)
class ProviderRef:
    """A cost-incurring provider at one stage: its family, selected kind and priced model id."""

    family: str
    kind: str
    model: str | None


@dataclass(frozen=True, slots=True)
class CostPlan:
    """Which stages spend, with what provider — everything the estimator needs from the config."""

    embed: ProviderRef | None
    embed_sparse: bool
    contextualize_llm: ProviderRef | None
    metagen_chunk: ProviderRef | None
    metagen_document: ProviderRef | None
    n_generated_chunk_fields: int
    n_generated_document_fields: int
    enrich_vlm: ProviderRef | None
    enrich_ocr: ProviderRef | None


class CostPlanExtractor:
    """Static extractor: PipelineState (+ contract field counts) → CostPlan."""

    def __new__(cls, *args: object, **kwargs: object) -> None:
        raise TypeError("CostPlanExtractor is a static-only class and cannot be instantiated.")

    @staticmethod
    def __head_model(config: dict, fallback: dict | None = None) -> str | None:
        """The model id a chain step declares, falling back to the stage's shared endpoint config."""
        model = config.get("model")
        if model:
            return str(model)
        if fallback and fallback.get("model"):
            return str(fallback["model"])
        return None

    @classmethod
    def __embed(cls, state: PipelineState) -> ProviderRef | None:
        """The embed provider (its head step), or None when the embed stage is off/empty."""
        if not state.embed_on or not state.embed_chain.steps:
            return None
        head = state.embed_chain.steps[0]
        return ProviderRef("embed", head.kind, cls.__head_model(head.config))

    @classmethod
    def __contextualize_llm(cls, state: PipelineState) -> ProviderRef | None:
        """The LLM contextualize method's provider, or None when no llm method is stacked."""
        for method in state.stack:
            if method.kind == "llm" and method.chain and method.chain.steps:
                head = method.chain.steps[0]
                return ProviderRef("llm", head.kind, cls.__head_model(head.config))
        return None

    @classmethod
    def __metagen(cls, on: bool, chain, config: dict) -> ProviderRef | None:
        """A metagen scope's structgen provider, or None when the scope is off/empty."""
        if not on or not chain.steps:
            return None
        head = chain.steps[0]
        return ProviderRef("structgen", head.kind, cls.__head_model(head.config, config))

    @classmethod
    def __enrich(cls, state: PipelineState, family: str) -> ProviderRef | None:
        """A representative paid provider of the enrich chains of one family (vlm / ocr)."""
        if not state.enrich_on:
            return None
        # 1. Prefer the first PAID step across the family's chains (a local head would price 0 and
        #    hide a real escalation cost); fall back to the first head when every step is local.
        head: object | None = None
        for spec in state.chains.values():
            if spec.family != family or not spec.steps:
                continue
            if head is None:
                head = spec.steps[0]
            for step in spec.steps:
                # Skip LOCAL (free) providers to find the first genuinely paid step. Use the canonical
                # LOCAL_FREE_KINDS (bge_server, rapidocr, paddle) — a hardcoded subset that omitted
                # paddle priced a [paddle -> mistral] OCR escalation at $0.00, hiding the Mistral cost.
                if step.kind not in LOCAL_FREE_KINDS:
                    return ProviderRef(family, step.kind, cls.__head_model(step.config))
        if head is None:
            return None
        return ProviderRef(family, head.kind, cls.__head_model(head.config))  # type: ignore[attr-defined]

    @classmethod
    def extract(
        cls,
        state: PipelineState,
        n_generated_chunk_fields: int,
        n_generated_document_fields: int,
    ) -> CostPlan:
        """
        Derive the cost plan from a pipeline state and the contract's generated-field counts.

        Args:
            state (PipelineState): The collection's canonical pipeline config.
            n_generated_chunk_fields (int): Contract fields generated per chunk (scope=chunk).
            n_generated_document_fields (int): Contract fields generated per document (scope=document).

        Returns:
            CostPlan: The neutral description of every cost-incurring stage.
        """
        embed = cls.__embed(state)
        embed_sparse = bool(
            state.embed_on
            and state.embed_chain.steps
            and state.embed_chain.steps[0].config.get("embed_sparse", True)
        )
        return CostPlan(
            embed=embed,
            embed_sparse=embed_sparse,
            contextualize_llm=cls.__contextualize_llm(state),
            metagen_chunk=cls.__metagen(
                state.metachunk_on, state.metachunk_chain, state.metachunk_config
            ),
            metagen_document=cls.__metagen(
                state.metadoc_on, state.metadoc_chain, state.metadoc_config
            ),
            n_generated_chunk_fields=n_generated_chunk_fields,
            n_generated_document_fields=n_generated_document_fields,
            enrich_vlm=cls.__enrich(state, "vlm"),
            enrich_ocr=cls.__enrich(state, "ocr"),
        )


__all__ = ["ProviderRef", "CostPlan", "CostPlanExtractor"]
