# ====== Code Summary ======
# StageUsageSummer — totals a stage's paid text-generation usage over its WHOLE execution tree,
# priced per leaf. Only leaf action records carry ``usage`` (groups/foreach wrappers do not), and a
# stage may fan out over MIXED models (a foreach whose items escalated to different providers), so
# each leaf is priced individually and the costs summed — never a single-model assumption.

# ====== Third-Party Library Imports ======
from loggerplusplus import loggerplusplus

# ====== Internal Project Imports ======
from shared_libs.pipelines.base import NodeExecutionRecord
from shared_libs.pipelines.ingest.estimate import RateTable


class StageUsageSummer:
    """Static helper: sum + price a stage's paid text-gen usage over its execution tree."""

    logger = loggerplusplus.bind(identifier="StageUsageSummer")

    def __new__(cls, *args: object, **kwargs: object) -> None:
        raise TypeError("StageUsageSummer is a static-only class and cannot be instantiated.")

    @classmethod
    def summarize(
        cls, record: NodeExecutionRecord, rates: RateTable
    ) -> tuple[int, int, float | None, int]:
        """
        Total a stage's paid-call usage over its execution tree, priced per leaf against ``rates``.

        The rate table is the collection's effective one (defaults folded with its per-collection rate
        overrides) — the SAME numbers the pre-hoc estimator used, so actual spend and its estimate are
        priced identically. Cost is None when NO leaf's model is priceable (the UI shows tokens but a
        "—" cost) rather than a fabricated zero; the summed cost otherwise (unpriceable leaves
        contribute tokens, no cost).

        Args:
            record (NodeExecutionRecord): The stage's record (recursed into its children).
            rates (RateTable): The collection's effective rate table (defaults + rate overrides).

        Returns:
            tuple[int, int, float | None, int]: (prompt tokens, completion tokens, USD cost or None,
                number of leaves that carried usage).
        """
        prompt = 0
        completion = 0
        cost = 0.0
        priced = False
        usage_count = 0

        # 1. Price THIS node's own paid call (a leaf action stamps ``usage``; wrappers leave it None).
        #    Two billing shapes coexist: token-billed calls (LLM/VLM/structgen/embed) price against
        #    ``rates.token_cost``, while a per-page OCR call (``usage.pages`` set, no tokens) prices
        #    against ``rates.ocr_cost`` — its cost folds into the same total, contributing 0 tokens.
        if record.usage is not None:
            usage = record.usage
            prompt += usage.prompt_tokens
            completion += usage.completion_tokens
            usage_count += 1
            leaf_cost = (
                rates.ocr_cost(usage.model, usage.pages)
                if usage.pages > 0
                else rates.token_cost(usage.model, usage.prompt_tokens, usage.completion_tokens)
            )
            if leaf_cost is not None:
                cost += leaf_cost
                priced = True

        # 2. Fold in every child's total (per-figure/per-chunk calls are nested child records).
        for child in record.children:
            child_prompt, child_completion, child_cost, child_count = cls.summarize(child, rates)
            prompt += child_prompt
            completion += child_completion
            usage_count += child_count
            if child_cost is not None:
                cost += child_cost
                priced = True

        return prompt, completion, (cost if priced else None), usage_count


__all__ = ["StageUsageSummer"]
