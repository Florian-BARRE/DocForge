# ====== Code Summary ======
# ConfigValidator — static orchestrator that runs all per-concern coherence checks against a
# collection config document.  Delegates to four checker modules (pipeline, locality, provider,
# metadata) and aggregates their issues into a single flat list.

# ====== Standard Library Imports ======
from __future__ import annotations

from typing import Any

# ====== Local Project Imports ======
from .locality_checks import LocalityChecks
from .metadata_checks import MetadataChecks
from .pipeline_checks import PipelineChecks
from .provider_checks import ProviderChecks


class ConfigValidator:
    """
    Static-only coherence validator for a collection config document.

    Orchestrates five distinct coherence checks in sequence:
    1. Contract scalars (locality policy + embedding model).
    2. Pipeline well-formedness (Pydantic parse).
    3. Inter-stage dependency invariants (reserved — pipeline is linear).
    4. Locality ↔ provider conflicts.
    5. Provider selectability and availability.
    6. Metadata field schema sanity.

    Produces a flat list of issues (errors + warnings).  A config with any ``error`` issue must
    not be applied; warnings are advisory (e.g. a remote provider whose key is not yet set).
    """

    def __new__(cls, *args: object, **kwargs: object) -> None:
        raise TypeError("ConfigValidator is a static-only class and cannot be instantiated.")

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
        PipelineChecks.check_contract(doc, issues)

        # 2. Pipeline well-formedness — if it does not even parse, stop here
        pipeline = PipelineChecks.parse_pipeline(doc, issues)
        if pipeline is None:
            return issues

        # 3. Inter-stage dependencies + locality ↔ provider conflicts + selectability
        PipelineChecks.check_step_dependencies(pipeline, issues)
        LocalityChecks.check_locality(doc.get("locality_policy"), pipeline, issues)
        provider_index = ProviderChecks.build_provider_index(stages)
        ProviderChecks.check_providers(pipeline, provider_index, issues)

        # 4. Metadata schema sanity
        MetadataChecks.check_metadata(doc.get("metadata_fields", []), issues)

        return issues
