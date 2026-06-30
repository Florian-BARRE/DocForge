# ====== Code Summary ======
# MetagenPromptHelpers — static, I/O-free helpers shared by the metagen nodes: partition targets by
# scope, build the per-field rule block, the chunk-scope and document-scope prompts, the document
# digest, and a coarse per-call cost estimate for the budget gate. Extracted so every node stays
# small and the prompt/cost logic is independently unit-testable without a provider or a network call.

# ====== Standard Library Imports ======
from typing import Any

# ====== Internal Project Imports ======
from common_libs.domain import MetaFieldSpec

# Coarse token/cost heuristics used ONLY by the ingestion budget gate (max_budget_usd). They are
# intentionally rough: ~4 chars/token, plus a flat per-1k-token price. Local LLMs are effectively
# free, so the realistic posture is max_budget_usd=0 (disabled); the estimate exists so an external
# provider cannot run away with thousands of per-chunk calls unbounded.
_CHARS_PER_TOKEN = 4
_EST_USD_PER_1K_TOKENS = 0.0002
# Max characters of document body folded into the document-scope digest prompt.
_DOC_DIGEST_MAX_CHARS = 4000
# Output token budget for one structured-metadata call (both scopes).
METAGEN_MAX_OUTPUT_TOKENS = 512


class MetagenPromptHelpers:
    """
    Static helpers for the metagen nodes (target partitioning, prompts, cost estimate).

    No instance state and no I/O — every method is a pure function over its arguments so the
    prompt shaping and cost heuristics can be unit-tested without a provider or a network call.
    """

    def __new__(cls, *args: object, **kwargs: object) -> None:  # type: ignore[misc]
        """Block instantiation — this is a static-only helper class."""
        raise TypeError("MetagenPromptHelpers is a static-only class and cannot be instantiated.")

    @staticmethod
    def scope_targets(
        targets: list[Any], field_types: dict[str, MetaFieldSpec], scope: str
    ) -> list[Any]:
        """
        Select the resolvable targets of one scope.

        Args:
            targets (list[MetaGenTarget]): All configured targets.
            field_types (dict[str, MetaFieldSpec]): Resolved type lookup (unknown fields skipped).
            scope (str): The scope to keep ("chunk" or "document").

        Returns:
            list[MetaGenTarget]: Targets matching ``scope`` whose field has a known type.
        """
        return [t for t in targets if t.scope == scope and t.field in field_types]

    @staticmethod
    def field_rules(targets: list[Any], field_types: dict[str, MetaFieldSpec]) -> str:
        """
        Render the per-field instruction block shared by every prompt of one scope.

        Args:
            targets (list[MetaGenTarget]): The scope-group's targets.
            field_types (dict[str, MetaFieldSpec]): Resolved type lookup (unknown fields skipped).

        Returns:
            str: One ``- name (type): prompt`` line per resolvable target.
        """
        lines: list[str] = []
        for target in targets:
            spec = field_types.get(target.field)
            if spec is None:
                continue
            rule = (target.prompt or "").strip() or "Extract this field."
            lines.append(f"- {target.field} ({spec.field_type}): {rule}")
        return "\n".join(lines)

    @staticmethod
    def build_chunk_prompt(rules: str, heading_path: str, raw_text: str) -> str:
        """
        Build the chunk-scope extraction prompt (one combined call per chunk).

        Args:
            rules (str): The shared per-field rule block.
            heading_path (str): The chunk's heading breadcrumb (may be empty).
            raw_text (str): The chunk's faithful text.

        Returns:
            str: The full prompt for ``generate_json``.
        """
        heading = heading_path.strip() or "(none)"
        return (
            "Extract the requested metadata from the text chunk below. "
            "Respond with ONLY a JSON object matching the schema.\n\n"
            f"Fields to extract:\n{rules}\n\n"
            f"Section: {heading}\n\n"
            f"Chunk text:\n{raw_text}"
        )

    @classmethod
    def build_doc_prompt(cls, rules: str, title: str, body: str) -> str:
        """
        Build the document-scope extraction prompt (one call per document).

        Args:
            rules (str): The shared per-field rule block.
            title (str): The document title (may be empty).
            body (str): Concatenated document body text (truncated to the digest budget).

        Returns:
            str: The full prompt for ``generate_json``.
        """
        digest = body[:_DOC_DIGEST_MAX_CHARS]
        return (
            "Extract the requested document-level metadata from the digest below. "
            "Respond with ONLY a JSON object matching the schema.\n\n"
            f"Fields to extract:\n{rules}\n\n"
            f"Title: {title or '(none)'}\n\n"
            f"Document digest:\n{digest}"
        )

    @staticmethod
    def document_digest(ir: Any) -> str:
        """
        Concatenate the text-bearing blocks of an IR into a single digest string.

        Args:
            ir (DocumentIR): The final IR.

        Returns:
            str: Newline-joined block text (untruncated; the prompt builder truncates).
        """
        parts = [b.text for b in getattr(ir, "blocks", []) if getattr(b, "text", None)]
        return "\n".join(parts)

    @classmethod
    def estimate_total(
        cls,
        chunks: list[Any],
        chunk_targets: list[Any],
        doc_targets: list[Any],
        ir: Any,
        field_types: dict[str, MetaFieldSpec],
    ) -> float:
        """
        Estimate the total USD cost of a document's metagen run for the budget gate.

        One combined call per chunk for chunk-scope targets plus one call for document-scope targets.
        The per-call input proxy is the rule block + the content text (no full prompt is built,
        keeping the estimate cheap over thousands of chunks).

        Args:
            chunks (list[Chunk]): The document's chunks.
            chunk_targets (list[MetaGenTarget]): Resolvable chunk-scope targets.
            doc_targets (list[MetaGenTarget]): Resolvable document-scope targets.
            ir (DocumentIR): The final IR (document-scope digest source).
            field_types (dict[str, MetaFieldSpec]): Resolved type lookup.

        Returns:
            float: The estimated total cost in USD.
        """
        total = 0.0
        # 1. Chunk-scope: one call per chunk (rules + the chunk's own text as the input proxy).
        if chunk_targets:
            rules = cls.field_rules(chunk_targets, field_types)
            for chunk in chunks:
                total += cls.estimate_call_cost(rules + chunk.raw_text, METAGEN_MAX_OUTPUT_TOKENS)
        # 2. Document-scope: a single call over the truncated digest.
        if doc_targets:
            rules = cls.field_rules(doc_targets, field_types)
            digest = cls.document_digest(ir)[:_DOC_DIGEST_MAX_CHARS]
            total += cls.estimate_call_cost(rules + digest, METAGEN_MAX_OUTPUT_TOKENS)
        return total

    @classmethod
    def estimate_call_cost(cls, prompt_text: str, max_tokens: int) -> float:
        """
        Coarsely estimate the USD cost of one LLM call for the ingestion budget gate.

        Args:
            prompt_text (str): The prompt that will be sent (input tokens proxy).
            max_tokens (int): The output token budget.

        Returns:
            float: A rough cost estimate in USD (input + output tokens times flat price).
        """
        input_tokens = len(prompt_text) / _CHARS_PER_TOKEN
        total_tokens = input_tokens + max_tokens
        return (total_tokens / 1000.0) * _EST_USD_PER_1K_TOKENS


__all__ = ["MetagenPromptHelpers", "METAGEN_MAX_OUTPUT_TOKENS"]
