# ====== Code Summary ======
# PipelineChecks — validates pipeline contract scalars (locality policy, embedding model)
# and inter-stage dependency well-formedness.  Pure static validation logic; no logging.

# ====== Standard Library Imports ======
from __future__ import annotations

from typing import Any

# ====== Third-Party Library Imports ======
from pydantic import ValidationError

# ====== Internal Project Imports ======
from common_libs.config.pipeline import PipelineConfig

# Locality policies the platform understands.
_ALLOWED_LOCALITY: frozenset[str] = frozenset({"on_premise_only", "external_allowed"})


class PipelineChecks:
    """
    Static checker for pipeline contract scalars and well-formedness.

    Validates:
    - ``locality_policy`` is one of the known values.
    - ``embedding_model`` is present (immutable per vector space).
    - The ``pipeline`` block can be parsed into a valid ``PipelineConfig``.
    - (Reserved) Inter-stage dependency invariants (currently a no-op — pipeline is linear S0→S6).
    """

    def __new__(cls, *args: object, **kwargs: object) -> None:
        raise TypeError("PipelineChecks is a static-only class and cannot be instantiated.")

    @staticmethod
    def check_contract(doc: dict[str, Any], issues: list[dict[str, Any]]) -> None:
        """
        Validate the locality policy and the mandatory embedding model scalar.

        Args:
            doc (dict): The canonical config document.
            issues (list[dict]): Accumulator — issues are appended in place.
        """
        locality = doc.get("locality_policy")
        if locality not in _ALLOWED_LOCALITY:
            issues.append(_issue(
                "locality.unknown", "error", "locality_policy",
                f"locality_policy must be one of {sorted(_ALLOWED_LOCALITY)}, got {locality!r}.",
            ))
        if not doc.get("embedding_model"):
            issues.append(_issue(
                "embedding_model.missing", "error", "embedding_model",
                "embedding_model is required — it fixes the collection's vector space.",
            ))

    @staticmethod
    def parse_pipeline(doc: dict[str, Any], issues: list[dict[str, Any]]) -> PipelineConfig | None:
        """
        Attempt to parse the pipeline block into a ``PipelineConfig``.

        Appends a terminal ``pipeline.invalid`` error and returns ``None`` on failure so the
        caller can short-circuit further checks that require a valid pipeline object.

        Args:
            doc (dict): The canonical config document.
            issues (list[dict]): Accumulator — issues are appended in place.

        Returns:
            PipelineConfig | None: Parsed config, or ``None`` if parsing failed.
        """
        try:
            return PipelineConfig.from_dict(doc.get("pipeline"))
        except ValidationError as exc:
            issues.append(_issue(
                "pipeline.invalid", "error", "pipeline",
                f"Pipeline config is malformed: {exc.error_count()} error(s).",
            ))
            return None

    @staticmethod
    def check_step_dependencies(
        pipeline: PipelineConfig, issues: list[dict[str, Any]]
    ) -> None:
        """
        Validate inter-stage / intra-stage coherence invariants.

        The ingestion pipeline (S0→S6) is fixed and linear, so there is nothing to
        check there.  The search stage, however, has a toggle whose chain must be
        coherent: ``search.rerank.enabled`` requires a configured provider chain.

        Args:
            pipeline (PipelineConfig): The parsed pipeline config.
            issues (list[dict]): Accumulator — issues are appended in place.
        """
        # 1. Rerank coherence: enabled without a provider chain silently no-ops at runtime.
        PipelineChecks._check_rerank_chain(pipeline, issues)

    @staticmethod
    def _check_rerank_chain(
        pipeline: PipelineConfig, issues: list[dict[str, Any]]
    ) -> None:
        """
        Flag an enabled rerank stage that has no provider configured.

        A config with ``search.rerank.enabled == true`` but an empty ``chain`` cannot
        rerank anything: the engine builder silently skips reranking, so the user
        believes reranking is active when it is not.  This is an ERROR-severity issue
        so saving such a config is rejected (422) rather than stored in a broken state.

        Args:
            pipeline (PipelineConfig): The parsed pipeline config.
            issues (list[dict]): Accumulator — issues are appended in place.
        """
        rerank = pipeline.search.rerank
        if rerank.enabled and len(rerank.chain) == 0:
            issues.append(_issue(
                "search.rerank.empty_chain", "error", "pipeline.search.rerank.chain",
                "rerank is enabled but no rerank provider is configured "
                "(search.rerank.chain is empty).",
            ))


# ─── Module-level helper (not exposed in __all__) ────────────────────────────

def _issue(code: str, severity: str, field: str, message: str) -> dict[str, Any]:
    """Build a single validation issue record."""
    return {"code": code, "severity": severity, "field": field, "message": message}
