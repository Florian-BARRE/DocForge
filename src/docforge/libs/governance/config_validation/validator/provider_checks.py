# ====== Code Summary ======
# ProviderChecks — validates that every selected provider is selectable and available in the
# current deployment.  Emits errors for unknown/non-selectable providers and warnings for
# selectable-but-unavailable ones without credentials.  Pure static validation logic; no logging.

# ====== Standard Library Imports ======
from __future__ import annotations

from typing import Any

# ====== Internal Project Imports ======
from libs.core.contracts.pipeline_config import PipelineConfig


class ProviderChecks:
    """
    Static checker for provider selectability and availability.

    Iterates all provider selections across parse, split, classify, OCR, VLM, and embed chains
    and cross-references each against the live stage schema index.
    """

    def __new__(cls, *args: object, **kwargs: object) -> None:
        raise TypeError("ProviderChecks is a static-only class and cannot be instantiated.")

    @staticmethod
    def build_provider_index(
        stages: list[dict[str, Any]],
    ) -> dict[tuple[str, str], dict[str, Any]]:
        """
        Flatten the stage schema into a ``{(capability, provider_id): provider}`` lookup.

        Args:
            stages (list[dict]): ``registry.describe_stages()["stages"]`` — the live schema.

        Returns:
            dict: Lookup mapping ``(capability, provider_id)`` to the provider descriptor dict.
        """
        index: dict[tuple[str, str], dict[str, Any]] = {}
        for stage in stages:
            for group in stage.get("groups", []):
                capability = group.get("capability")
                for prov in group.get("providers", []):
                    index[(capability, prov["id"])] = prov
        return index

    @staticmethod
    def check_providers(
        pipeline: PipelineConfig,
        index: dict[tuple[str, str], dict[str, Any]],
        issues: list[dict[str, Any]],
    ) -> None:
        """
        Check every selected provider is selectable; warn when not yet available.

        Args:
            pipeline (PipelineConfig): The parsed pipeline config.
            index (dict): Provider index built by ``build_provider_index``.
            issues (list[dict]): Accumulator — issues are appended in place.
        """
        # 1. Parse chain — every provider in declaration order
        for parse in pipeline.parse.chain:
            ProviderChecks._check_one("parse", parse.id, _params_dict(parse), index, issues)
        # 1b. Chunk split method (decision-tree-by-method): unknown id → error; semantic needs TEI
        split = pipeline.chunk.split_method
        ProviderChecks._check_one("split_method", split.id, _params_dict(split), index, issues)
        # 2. S2 enrichment chains — classifier / ocr / vlm
        for classifier in pipeline.enrich.classifier_chain:
            ProviderChecks._check_one(
                "classifier", classifier.id, _params_dict(classifier), index, issues
            )
        for spec in pipeline.enrich.ocr_chain:
            ProviderChecks._check_one("ocr", spec.id, _params_dict(spec), index, issues)
        for vlm in pipeline.enrich.vlm_chain:
            ProviderChecks._check_one("vlm", vlm.id, _params_dict(vlm), index, issues)
        # 3. Embedding chain
        for embed in pipeline.embed.chain:
            ProviderChecks._check_one("embed", embed.id, _params_dict(embed), index, issues)

    @staticmethod
    def _check_one(
        capability: str,
        provider_id: str,
        params: dict[str, Any],
        index: dict[tuple[str, str], dict[str, Any]],
        issues: list[dict[str, Any]],
    ) -> None:
        """
        Validate a single provider selection against the live schema.

        Args:
            capability (str): The capability group (e.g. ``"parse"``, ``"ocr"``).
            provider_id (str): The provider discriminator (e.g. ``"docling"``).
            params (dict): Provider parameters (used to check for inline credentials).
            index (dict): Provider lookup built by ``build_provider_index``.
            issues (list[dict]): Accumulator — issues are appended in place.
        """
        # 1. Provider must exist for this capability
        prov = index.get((capability, provider_id))
        if prov is None:
            issues.append(_issue(
                f"{capability}.unknown", "error", capability,
                f"Unknown {capability} provider {provider_id!r}.",
            ))
            return

        # 2. Must be selectable in this deployment (e.g. local package present)
        if not prov.get("selectable", False):
            issues.append(_issue(
                f"{capability}.not_selectable", "error", capability,
                prov.get("note") or f"Provider {provider_id!r} is not selectable here.",
            ))
            return

        # 3. Selectable but not yet available → advisory unless credentials are supplied in params
        if not prov.get("available", False):
            has_creds = bool(params.get("api_key") or params.get("base_url"))
            if not has_creds:
                issues.append(_issue(
                    f"{capability}.unavailable", "warning", capability,
                    prov.get("note") or f"Provider {provider_id!r} is not currently available.",
                ))


# ─── Module-level helpers (not exposed in __all__) ───────────────────────────

def _params_dict(provider: Any) -> dict[str, Any]:
    """
    Return the provider's params as a plain dict, agnostic of the post-refactor flat shape.

    Typed Pydantic provider configs (DoclingConfig, TeiEmbedConfig, …) carry their params as
    flat top-level fields with ``id`` as the discriminator — ``model_dump(exclude={"id"})``
    yields the dict the rest of the validator (and _check_one) expects. The fallback handles
    the legacy ProviderSpec(id, params) shape still kept in pipeline_config for compat.

    Args:
        provider (Any): A provider config object (typed Pydantic or legacy ProviderSpec).

    Returns:
        dict: Provider parameters as a plain dict.
    """
    # 1. Typed Pydantic v2 config → flat dict excluding the discriminator
    if hasattr(provider, "model_dump"):
        try:
            return provider.model_dump(exclude={"id"})
        except Exception:  # noqa: BLE001 — fall back to attribute access on a stale model
            pass
    # 2. Legacy ProviderSpec(id, params) — kept for backward compat
    return dict(getattr(provider, "params", {}) or {})


def _issue(code: str, severity: str, field: str, message: str) -> dict[str, Any]:
    """Build a single validation issue record."""
    return {"code": code, "severity": severity, "field": field, "message": message}
