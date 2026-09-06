# ====== Code Summary ======
# RateTable — the pure, passed-in rate model the estimator prices against. It carries the three rate
# maps (chat input/output, embedding, per-page OCR) and answers "what does this call cost?" with a
# clear known/unknown distinction: an unknown model returns None (never a fabricated number). Its
# ``default()`` factory seeds from the ONE canonical rate source (openai_compat.pricing) so a pre-hoc
# estimate and its later post-hoc actual are priced from identical numbers. The estimator receives a
# RateTable — it never reads the pricing module directly — so callers can override rates per request.

# ====== Standard Library Imports ======
from dataclasses import dataclass, field

# ====== Internal Project Imports ======
from shared_libs.pipelines.nodes.openai_compat import (
    EMBED_PRICING,
    MODEL_PRICING,
    OCR_PAGE_PRICING,
)

# Provider kinds that run locally / in-stack and therefore cost nothing — priced 0 (a KNOWN rate),
# distinct from a paid provider whose model is missing from the tables (unknown ⇒ None).
LOCAL_FREE_KINDS: frozenset[str] = frozenset({"bge_server", "rapidocr", "paddle"})


@dataclass(frozen=True, slots=True)
class RateTable:
    """
    An immutable rate model: chat (input, output), embedding, and per-page OCR rates in USD.

    Attributes:
        chat (dict[str, tuple[float, float]]): Model id → (input, output) USD per 1M tokens.
        embed (dict[str, float]): Embedding model id → USD per 1M tokens.
        ocr_per_page (dict[str, float]): OCR provider kind → USD per page.
    """

    chat: dict[str, tuple[float, float]] = field(default_factory=dict)
    embed: dict[str, float] = field(default_factory=dict)
    ocr_per_page: dict[str, float] = field(default_factory=dict)

    @classmethod
    def default(cls) -> "RateTable":
        """Build the default rate table from the canonical pricing source."""
        return cls(
            chat=dict(MODEL_PRICING),
            embed=dict(EMBED_PRICING),
            ocr_per_page=dict(OCR_PAGE_PRICING),
        )

    @classmethod
    def from_overrides(cls, overrides: dict | None) -> "RateTable":
        """
        Build the effective rate table: the canonical defaults with a collection's rate overrides
        merged in per-key. This is the ONE fold used by BOTH the pre-hoc estimator and the post-hoc
        meter, so an estimate and its later actual are priced from identical numbers even when a
        collection carries negotiated rates.

        Args:
            overrides (dict | None): The collection's stored ``estimate_overrides`` JSONB (or None).
                Only its ``rates`` subtree is read: ``{"models": {id: {"input", "output"}}, "embed":
                {id: rate}, "ocr": {kind: rate}}``. Any subtree may be absent → that map is the
                default; a provided entry overlays only its own key (never a wholesale replace).

        Returns:
            RateTable: The defaults when no rate override is present, else the per-key merge.
        """
        # 1. Always start from the canonical source (keeps estimate ↔ actual consistent).
        base = cls.default()
        rates = (overrides or {}).get("rates")
        if not rates:
            return base

        # 2. Copy each default map, then overlay only the provided entries.
        chat = dict(base.chat)
        for model, rate in (rates.get("models") or {}).items():
            chat[model] = (rate["input"], rate["output"])
        embed = dict(base.embed)
        embed.update(rates.get("embed") or {})
        ocr = dict(base.ocr_per_page)
        ocr.update(rates.get("ocr") or {})
        return cls(chat=chat, embed=embed, ocr_per_page=ocr)

    def token_cost(
        self, model: str, prompt_tokens: float, completion_tokens: float
    ) -> float | None:
        """
        USD for a token-billed call, trying the chat rate first then the embed rate — the RateTable
        sibling of ``openai_compat.price_usd`` (a paid embedding call has ``completion_tokens`` 0 and a
        single input rate). None when the model is in neither map.
        """
        chat = self.chat_cost(model, prompt_tokens, completion_tokens)
        if chat is not None:
            return chat
        return self.embed_cost(model, prompt_tokens)

    def chat_cost(self, model: str, prompt_tokens: float, completion_tokens: float) -> float | None:
        """USD for a chat/LLM/VLM call, or None when the model has no known rate."""
        rates = self.chat.get(model)
        if rates is None:
            return None
        input_rate, output_rate = rates
        return prompt_tokens / 1e6 * input_rate + completion_tokens / 1e6 * output_rate

    def embed_cost(self, model: str, tokens: float) -> float | None:
        """USD for embedding ``tokens``, or None when the model has no known rate."""
        rate = self.embed.get(model)
        if rate is None:
            return None
        return tokens / 1e6 * rate

    def ocr_cost(self, kind: str, pages: float) -> float | None:
        """USD for OCR-ing ``pages`` with a provider kind, or None when the kind has no known rate."""
        rate = self.ocr_per_page.get(kind)
        if rate is None:
            return None
        return pages * rate


__all__ = ["RateTable", "LOCAL_FREE_KINDS"]
