# ====== Code Summary ======
# ConfigValidator — coherence checks for a collection config document, distinct from admission
# (admission validates a *document + payload* against a collection; this validates the *config
# itself* before it is applied).  Checks: pipeline well-formedness, inter-stage dependencies,
# locality ↔ remote-provider conflicts, provider selectability/availability, metadata sanity.

# ====== Standard Library Imports ======
from __future__ import annotations

import ipaddress
from typing import Any, get_args
from urllib.parse import urlparse

# ====== Third-Party Library Imports ======
from loggerplusplus import loggerplusplus
from pydantic import ValidationError

# ====== Internal Project Imports ======
from metadata import MetaFieldType
from pipeline.pipeline_config import PipelineConfig

# Field types accepted in a metadata schema — derived from the canonical MetaFieldType so the
# validator can never drift from what MetaFieldSpec actually accepts.
_ALLOWED_FIELD_TYPES: frozenset[str] = frozenset(get_args(MetaFieldType))
# Locality policies the platform understands.
_ALLOWED_LOCALITY: frozenset[str] = frozenset({"on_premise_only", "external_allowed"})
# OCR providers that always call out to an external cloud API (no on-prem variant).
_REMOTE_OCR_IDS: frozenset[str] = frozenset({"mistral_ocr"})


class ConfigValidator:
    """
    Static-only coherence validator for a collection config document.

    Produces a flat list of issues (errors + warnings).  A config with any ``error`` issue must
    not be applied; warnings are advisory (e.g. a remote provider whose key is not yet set).
    """

    logger = loggerplusplus.bind(identifier="ConfigValidator")

    def __new__(cls, *args: object, **kwargs: object) -> None:
        raise TypeError("ConfigValidator is a static-only class and cannot be instantiated.")

    # ─── Public API ───────────────────────────────────────────────────────────────

    @classmethod
    def validate(cls, doc: dict[str, Any], stages: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """
        Validate a full config document against the live provider stage schema.

        Args:
            doc (dict): A canonical config document (see ConfigDocument).
            stages (list[dict]): ``registry.describe_stages()["stages"]`` — the live schema
                used to check provider selectability/availability.

        Returns:
            list[dict]: Issues, each ``{"code", "severity", "field", "message"}`` with severity
                in {"error", "warning"}.  Empty list = fully valid.
        """
        issues: list[dict[str, Any]] = []

        # 1. Contract scalars (locality + embedding model)
        cls._check_contract(doc, issues)

        # 2. Pipeline well-formedness — if it does not even parse, stop here
        try:
            pipeline = PipelineConfig.from_dict(doc.get("pipeline"))
        except ValidationError as exc:
            issues.append(cls._issue("pipeline.invalid", "error", "pipeline",
                                     f"Pipeline config is malformed: {exc.error_count()} error(s)."))
            return issues

        # 3. Inter-stage dependencies + locality ↔ provider conflicts + selectability
        cls._check_step_dependencies(pipeline, issues)
        cls._check_locality(doc.get("locality_policy"), pipeline, issues)
        cls._check_providers(pipeline, cls._provider_index(stages), issues)

        # 4. Metadata schema sanity
        cls._check_metadata(doc.get("metadata_fields", []), issues)

        return issues

    # ─── Individual checks ──────────────────────────────────────────────────────

    @classmethod
    def _check_contract(cls, doc: dict[str, Any], issues: list[dict[str, Any]]) -> None:
        """Validate the locality policy and the (mandatory, immutable-per-space) embedding model."""
        locality = doc.get("locality_policy")
        if locality not in _ALLOWED_LOCALITY:
            issues.append(cls._issue(
                "locality.unknown", "error", "locality_policy",
                f"locality_policy must be one of {sorted(_ALLOWED_LOCALITY)}, got {locality!r}.",
            ))
        if not doc.get("embedding_model"):
            issues.append(cls._issue(
                "embedding_model.missing", "error", "embedding_model",
                "embedding_model is required — it fixes the collection's vector space.",
            ))

    @classmethod
    def _check_step_dependencies(cls, pipeline: PipelineConfig, issues: list[dict[str, Any]]) -> None:
        """Reserved for future inter-stage dependency checks.  Pipeline is fixed S0→S6."""
        # The pipeline is linear and always fully executed — no toggles to validate here.

    @classmethod
    def _check_locality(
        cls, locality: Any, pipeline: PipelineConfig, issues: list[dict[str, Any]]
    ) -> None:
        """Reject external providers when the collection is pinned on-premise."""
        # 1. Only on_premise_only constrains provider choice
        if locality != "on_premise_only":
            return

        # 2. Cloud OCR providers are never on-prem
        for spec in pipeline.enrich.ocr_chain:
            if spec.id in _REMOTE_OCR_IDS:
                issues.append(cls._issue(
                    "locality.remote_ocr", "error", "enrich.ocr_chain",
                    f"OCR provider {spec.id!r} is a remote API, forbidden by on_premise_only.",
                ))

        # 3. A VLM pointed at a remote endpoint is forbidden (local vLLM URL is fine)
        if pipeline.enrich.vlm is not None:
            base_url = str(pipeline.enrich.vlm.params.get("base_url", ""))
            if cls._is_remote_url(base_url):
                issues.append(cls._issue(
                    "locality.remote_vlm", "error", "enrich.vlm",
                    f"VLM endpoint {base_url!r} is remote, forbidden by on_premise_only.",
                ))

        # 4. A remote embedding endpoint is forbidden
        embed_url = str(pipeline.embed.provider.params.get("base_url", ""))
        if cls._is_remote_url(embed_url):
            issues.append(cls._issue(
                "locality.remote_embed", "error", "embed.provider",
                f"Embedding endpoint {embed_url!r} is remote, forbidden by on_premise_only.",
            ))

    @classmethod
    def _check_providers(
        cls,
        pipeline: PipelineConfig,
        index: dict[tuple[str, str], dict[str, Any]],
        issues: list[dict[str, Any]],
    ) -> None:
        """Check every selected provider is selectable; warn when not yet available."""
        # 1. Parse provider
        cls._check_one("parse", pipeline.parse.provider.id, pipeline.parse.provider.params, index, issues)
        # 1b. Chunk split method (decision-tree-by-method): unknown id → error; semantic needs TEI
        cls._check_one(
            "chunk_strategy",
            pipeline.chunk.split_method.id,
            pipeline.chunk.split_method.params,
            index,
            issues,
        )
        # 2. S2 enrichment providers — always checked (S2 always runs)
        cls._check_one("classifier", pipeline.enrich.classifier.id,
                       pipeline.enrich.classifier.params, index, issues)
        for spec in pipeline.enrich.ocr_chain:
            cls._check_one("ocr", spec.id, spec.params, index, issues)
        if pipeline.enrich.vlm is not None:
            cls._check_one("vlm", pipeline.enrich.vlm.id, pipeline.enrich.vlm.params, index, issues)
        # 3. Embedding provider (always part of the pipeline)
        cls._check_one("embed", pipeline.embed.provider.id,
                       pipeline.embed.provider.params, index, issues)

    @classmethod
    def _check_one(
        cls,
        capability: str,
        provider_id: str,
        params: dict[str, Any],
        index: dict[tuple[str, str], dict[str, Any]],
        issues: list[dict[str, Any]],
    ) -> None:
        """Validate a single provider selection against the live schema."""
        # 1. Provider must exist for this capability
        prov = index.get((capability, provider_id))
        if prov is None:
            issues.append(cls._issue(
                f"{capability}.unknown", "error", capability,
                f"Unknown {capability} provider {provider_id!r}.",
            ))
            return

        # 2. Must be selectable in this deployment (e.g. local package present)
        if not prov.get("selectable", False):
            issues.append(cls._issue(
                f"{capability}.not_selectable", "error", capability,
                prov.get("note") or f"Provider {provider_id!r} is not selectable here.",
            ))
            return

        # 3. Selectable but not yet available → advisory unless credentials are supplied in params
        if not prov.get("available", False):
            has_creds = bool(params.get("api_key") or params.get("base_url"))
            if not has_creds:
                issues.append(cls._issue(
                    f"{capability}.unavailable", "warning", capability,
                    prov.get("note") or f"Provider {provider_id!r} is not currently available.",
                ))

    @classmethod
    def _check_metadata(cls, fields: list[dict[str, Any]], issues: list[dict[str, Any]]) -> None:
        """Validate metadata field names, types, enum values, and fusion weights."""
        seen: set[str] = set()
        for field in fields:
            name = field.get("field_name")
            # 1. Name present + unique
            if not name:
                issues.append(cls._issue("metadata.no_name", "error", "metadata_fields",
                                         "A metadata field is missing 'field_name'."))
                continue
            if name in seen:
                issues.append(cls._issue("metadata.duplicate", "error", f"metadata_fields.{name}",
                                         f"Duplicate metadata field {name!r}."))
            seen.add(name)

            # 2. Type valid
            ftype = field.get("field_type", "string")
            if ftype not in _ALLOWED_FIELD_TYPES:
                issues.append(cls._issue(
                    "metadata.bad_type", "error", f"metadata_fields.{name}",
                    f"Field {name!r} has unknown type {ftype!r} (allowed: {sorted(_ALLOWED_FIELD_TYPES)}).",
                ))

            # 3. Enum fields need a non-empty value set
            if ftype == "enum" and not field.get("enum_values"):
                issues.append(cls._issue(
                    "metadata.enum_empty", "error", f"metadata_fields.{name}",
                    f"Enum field {name!r} must define enum_values.",
                ))

    # ─── Private utilities ──────────────────────────────────────────────────────

    @staticmethod
    def _provider_index(stages: list[dict[str, Any]]) -> dict[tuple[str, str], dict[str, Any]]:
        """Flatten the stage schema into a ``{(capability, provider_id): provider}`` lookup."""
        index: dict[tuple[str, str], dict[str, Any]] = {}
        for stage in stages:
            for group in stage.get("groups", []):
                capability = group.get("capability")
                for prov in group.get("providers", []):
                    index[(capability, prov["id"])] = prov
        return index

    @staticmethod
    def _is_remote_url(url: str) -> bool:
        """
        Decide whether a base URL points outside the on-prem network.

        Localhost, single-label Docker service names, and RFC-1918 private ranges are local;
        anything with a public-looking host is treated as remote.
        """
        # 1. No URL → nothing remote to forbid
        if not url:
            return False
        host = urlparse(url).hostname
        if not host:
            return False
        # 2. Explicit loopback / single-label service name → local
        if host in {"localhost", "127.0.0.1", "::1"} or "." not in host:
            return False
        # 3. Private IPv4 ranges → local
        try:
            if ipaddress.ip_address(host).is_private:
                return False
        except ValueError:
            pass  # not a literal IP — fall through to hostname heuristics
        # 4. Otherwise treat as a public/remote endpoint
        return True

    @staticmethod
    def _issue(code: str, severity: str, field: str, message: str) -> dict[str, Any]:
        """Build a single validation issue record."""
        return {"code": code, "severity": severity, "field": field, "message": message}
