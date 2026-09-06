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
# Rates verified 2026-09-06 against the providers' official pricing pages (OpenAI developers pricing;
# gpt-5.5 is the <272K-context tier). Cached-input discounts are NOT modelled (the meter cannot know
# a call's cache-hit ratio) — the standard non-cached input rate is used, a safe upper bound.
MODEL_PRICING: dict[str, tuple[float, float]] = {
    # GPT-4o / GPT-4.1 (still current, kept).
    "gpt-4o-mini": (0.15, 0.60),
    "gpt-4o": (2.50, 10.00),
    "gpt-4.1-mini": (0.40, 1.60),
    "gpt-4.1": (2.00, 8.00),
    # GPT-5 generation.
    "gpt-5": (1.25, 10.00),
    "gpt-5-mini": (0.25, 2.00),
    "gpt-5.5": (5.00, 30.00),
    "gpt-5.6-sol": (4.00, 20.00),
    "gpt-5.6-terra": (2.00, 12.00),
    "gpt-5.6-luna": (0.20, 1.20),
}

# Embedding model id → USD per 1M tokens (a single input rate; embeddings have no completion side).
# Used by BOTH the pre-hoc estimator (projected spend) and the post-hoc meter (``price_usd`` prices a
# paid embed leaf here — its ``completion_tokens`` is 0). The default bge_server embedder is local and
# free: it stamps no usage, so it never reaches this table. A locally hosted embedder is priced 0 by
# the estimator (a known-free provider), not looked up here; this table is for the paid, hosted ones.
# Rates verified 2026-09-06 (OpenAI + Mistral official pricing).
EMBED_PRICING: dict[str, float] = {
    "text-embedding-3-small": 0.02,
    "text-embedding-3-large": 0.13,
    "text-embedding-ada-002": 0.10,
    "mistral-embed": 0.10,
    "codestral-embed": 0.15,
}

# OCR provider kind → USD per page. OCR is priced per PAGE, not per token (that is how the hosted
# OCR providers bill). The local ``rapidocr``/``paddle`` kinds are free and are not listed here (the
# estimator prices them 0 as known-local providers, and they stamp no usage on their records). An
# absent paid kind prices to a null cost. Used by BOTH the pre-hoc estimator (projected spend) and
# the post-hoc meter (``price_ocr_pages`` prices a paid OCR leaf's ``NodeUsage.pages`` here).
# Rate verified 2026-09-06: Mistral OCR 4.1 standard API = $4 per 1000 pages (Document AI $5/1000 is a
# different endpoint, not this per-page OCR call). The 50% batch-API discount is not modelled.
OCR_PAGE_PRICING: dict[str, float] = {
    "mistral": 0.004,  # Mistral OCR 4.1: $4 per 1000 pages.
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


def price_ocr_pages(kind: str, pages: int) -> float | None:
    """
    Price a per-page OCR call in USD, or None when the OCR kind is not in ``OCR_PAGE_PRICING``.

    Hosted OCR bills per page, not per token, so this is the page-shaped sibling of ``price_usd``:
    the post-hoc meter routes a leaf whose ``NodeUsage.pages`` is set here. A free/local OCR kind
    (rapidocr, paddle) stamps no usage and never reaches this helper; an unknown paid kind prices to
    None so the caller can surface "—" instead of a fabricated cost.

    Args:
        kind (str): The OCR provider kind the leaf recorded as its ``NodeUsage.model`` (the key).
        pages (int): Pages billed for the call.

    Returns:
        float | None: The USD cost (0.0 for zero pages on a known kind), or None for an unknown kind.
    """
    rate = OCR_PAGE_PRICING.get(kind)
    if rate is None:
        return None
    return pages * rate


__all__ = ["MODEL_PRICING", "EMBED_PRICING", "OCR_PAGE_PRICING", "price_usd", "price_ocr_pages"]
