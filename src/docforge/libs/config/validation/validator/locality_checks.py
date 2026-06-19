# ====== Code Summary ======
# LocalityChecks — validates that provider selections do not violate the collection's locality
# policy (on_premise_only forbids cloud OCR, remote VLM endpoints, and remote embed endpoints).
# Pure static validation logic; no logging.

# ====== Standard Library Imports ======
from __future__ import annotations

import ipaddress
from typing import Any
from urllib.parse import urlparse

# ====== Internal Project Imports ======
from libs.core.contracts.pipeline_config import PipelineConfig

# OCR providers that always call out to an external cloud API (no on-prem variant).
_REMOTE_OCR_IDS: frozenset[str] = frozenset({"mistral_ocr"})


class LocalityChecks:
    """
    Static checker for locality policy ↔ provider conflicts.

    When ``locality_policy`` is ``on_premise_only``, forbids:
    - Cloud-only OCR providers (e.g. Mistral OCR).
    - VLM providers pointed at a public/remote base URL.
    - Embedding providers pointed at a public/remote base URL.
    """

    def __new__(cls, *args: object, **kwargs: object) -> None:
        raise TypeError("LocalityChecks is a static-only class and cannot be instantiated.")

    @staticmethod
    def check_locality(
        locality: Any, pipeline: PipelineConfig, issues: list[dict[str, Any]]
    ) -> None:
        """
        Reject external providers when the collection is pinned on-premise.

        Args:
            locality (Any): The ``locality_policy`` value from the config document.
            pipeline (PipelineConfig): The parsed pipeline config.
            issues (list[dict]): Accumulator — issues are appended in place.
        """
        # 1. Only on_premise_only constrains provider choice
        if locality != "on_premise_only":
            return

        # 2. Cloud OCR providers are never on-prem
        for spec in pipeline.enrich.ocr_chain:
            if spec.id in _REMOTE_OCR_IDS:
                issues.append(_issue(
                    "locality.remote_ocr", "error", "enrich.ocr_chain",
                    f"OCR provider {spec.id!r} is a remote API, forbidden by on_premise_only.",
                ))

        # 3. A VLM pointed at a remote endpoint is forbidden (local vLLM URL is fine)
        for vlm in pipeline.enrich.vlm_chain:
            base_url = str(getattr(vlm, "base_url", "") or "")
            if LocalityChecks._is_remote_url(base_url):
                issues.append(_issue(
                    "locality.remote_vlm", "error", "enrich.vlm_chain",
                    f"VLM endpoint {base_url!r} is remote, forbidden by on_premise_only.",
                ))

        # 4. A remote embedding endpoint is forbidden — apply to every provider in the chain
        for embed in pipeline.embed.chain:
            embed_url = str(getattr(embed, "base_url", "") or "")
            if LocalityChecks._is_remote_url(embed_url):
                issues.append(_issue(
                    "locality.remote_embed", "error", "embed.chain",
                    f"Embedding endpoint {embed_url!r} is remote, forbidden by on_premise_only.",
                ))
        if LocalityChecks._is_remote_url(embed_url):
            issues.append(_issue(
                "locality.remote_embed", "error", "embed.provider",
                f"Embedding endpoint {embed_url!r} is remote, forbidden by on_premise_only.",
            ))

    @staticmethod
    def _is_remote_url(url: str) -> bool:
        """
        Decide whether a base URL points outside the on-prem network.

        Localhost, single-label Docker service names, and RFC-1918 private ranges are local;
        anything with a public-looking host is treated as remote.

        Args:
            url (str): The URL string to inspect.

        Returns:
            bool: ``True`` if the URL resolves to a public/remote endpoint.
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


# ─── Module-level helper (not exposed in __all__) ────────────────────────────

def _issue(code: str, severity: str, field: str, message: str) -> dict[str, Any]:
    """Build a single validation issue record."""
    return {"code": code, "severity": severity, "field": field, "message": message}
