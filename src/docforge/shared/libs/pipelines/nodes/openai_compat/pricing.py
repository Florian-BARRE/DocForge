# ====== Code Summary ======
# The model → price table and the per-call cost helper. Token usage captured on the execution record
# is priced here into USD so the per-document / per-collection meter can show real money spent. An
# unknown model prices to None (the UI shows the token count but a "—" cost) rather than a fabricated
# number. Prices are USD per 1M tokens, (input, output), from the providers' public pricing.


# Model id → (input USD per 1M tokens, output USD per 1M tokens).
# Extend here as new models are used — an absent model prices to None (tokens shown, cost "—").
# This chat table is the canonical rate source for BOTH the post-hoc meter (actual spend, priced by
# ``price_usd``) and the pre-hoc estimator (projected spend) — so an estimate and its later actual
# use the same numbers. LLM and VLM calls (structgen + contextualize + figure captioning) price here;
# paid embeddings price against ``EMBED_PRICING`` below (an embedding call has input tokens only).
MODEL_PRICING: dict[str, tuple[float, float]] = {
    "gpt-4o-mini": (0.15, 0.60),
    "gpt-4o": (2.50, 10.00),
    "gpt-4.1-mini": (0.40, 1.60),
    "gpt-4.1": (2.00, 8.00),
}

# Embedding model id → USD per 1M tokens (a single input rate; embeddings have no completion side).
# Used by BOTH the pre-hoc estimator (projected spend) and the post-hoc meter (``price_usd`` prices a
# paid embed leaf here — its ``completion_tokens`` is 0). The default bge_server embedder is local and
# free: it stamps no usage, so it never reaches this table. A locally hosted embedder is priced 0 by
# the estimator (a known-free provider), not looked up here; this table is for the paid, hosted ones.
EMBED_PRICING: dict[str, float] = {
    "text-embedding-3-small": 0.02,
    "text-embedding-3-large": 0.13,
    "text-embedding-ada-002": 0.10,
}

# OCR provider kind → USD per page. OCR is priced per PAGE, not per token (that is how the hosted
# OCR providers bill). The local ``rapidocr`` kind is free and is not listed here (the estimator
# prices it 0 as a known-local provider). An absent paid kind estimates to a null cost.
OCR_PAGE_PRICING: dict[str, float] = {
    "mistral": 0.001,  # Mistral OCR: ~$1 per 1000 pages.
}


def price_usd(model: str, prompt_tokens: int, completion_tokens: int) -> float | None:
    """
    Price a single call's token usage in USD, or None when the model is not in either table.

    Chat/VLM/structgen calls price against ``MODEL_PRICING`` (input + output). A paid embedding call
    (``completion_tokens`` is always 0) whose model is absent from the chat table but present in
    ``EMBED_PRICING`` prices at its single input rate. An unknown model still prices to None so the
    caller can surface "—" instead of a fabricated cost.

    Args:
        model (str): The model id the call requested (the pricing-table key).
        prompt_tokens (int): Input tokens billed.
        completion_tokens (int): Output tokens billed.

    Returns:
        float | None: The USD cost (0.0 for zero tokens on a known model), or None for an unknown
            model — so the caller can surface "—" instead of a fabricated cost.
    """
    # 1. Chat/VLM/structgen: the (input, output) rate pair.
    rates = MODEL_PRICING.get(model)
    if rates is not None:
        input_rate, output_rate = rates
        return prompt_tokens / 1e6 * input_rate + completion_tokens / 1e6 * output_rate
    # 2. A paid embedding call (input tokens only): a single input rate, no completion side.
    embed_rate = EMBED_PRICING.get(model)
    if embed_rate is not None:
        return prompt_tokens / 1e6 * embed_rate
    # 3. Unknown model — tokens shown, cost "—".
    return None


__all__ = ["MODEL_PRICING", "EMBED_PRICING", "OCR_PAGE_PRICING", "price_usd"]
