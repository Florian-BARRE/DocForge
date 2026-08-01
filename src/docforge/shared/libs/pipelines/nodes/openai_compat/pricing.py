# ====== Code Summary ======
# The model → price table and the per-call cost helper. Token usage captured on the execution record
# is priced here into USD so the per-document / per-collection meter can show real money spent. An
# unknown model prices to None (the UI shows the token count but a "—" cost) rather than a fabricated
# number. Prices are USD per 1M tokens, (input, output), from the providers' public pricing.


# Model id → (input USD per 1M tokens, output USD per 1M tokens).
# Extend here as new models are used — an absent model prices to None (tokens shown, cost "—").
MODEL_PRICING: dict[str, tuple[float, float]] = {
    "gpt-4o-mini": (0.15, 0.60),
    "gpt-4o": (2.50, 10.00),
    "gpt-4.1-mini": (0.40, 1.60),
    "gpt-4.1": (2.00, 8.00),
}


def price_usd(model: str, prompt_tokens: int, completion_tokens: int) -> float | None:
    """
    Price a single call's token usage in USD, or None when the model is not in the table.

    Args:
        model (str): The model id the call requested (the pricing-table key).
        prompt_tokens (int): Input tokens billed.
        completion_tokens (int): Output tokens billed.

    Returns:
        float | None: The USD cost (0.0 for zero tokens on a known model), or None for an unknown
            model — so the caller can surface "—" instead of a fabricated cost.
    """
    rates = MODEL_PRICING.get(model)
    if rates is None:
        return None
    input_rate, output_rate = rates
    return prompt_tokens / 1e6 * input_rate + completion_tokens / 1e6 * output_rate


__all__ = ["MODEL_PRICING", "price_usd"]
