# ====== Code Summary ======
# The API response contract for GET /capabilities — the deployment self-description: running version,
# auth state, derived GPU presence, the infra stores + optional sidecars (reachability + what each
# unlocks), and the available pipeline kinds per family. Kept next to the service that builds it (the
# codebase convention for a service-backed router — see libs/health/models.py), imported by the router.

# ====== Third-Party Library Imports ======
from pydantic import BaseModel, ConfigDict, Field


class ServiceInfo(BaseModel):
    """
    One infra store or optional sidecar of the deployment.

    Attributes:
        name (str): Stable service name (compose service / network alias).
        role (str): Short role label (e.g. ``"vector"``, ``"embed"``, ``"parse-ocr"``).
        reachable (bool): For a sidecar, whether its short-cached ``/health`` probe currently passes;
            for an infra store, whether it is configured (declared, not live-probed — see ``detail``).
        device (str | None): The compute device the sidecar reports at ``/health`` (``"cuda"``/``"cpu"``)
            when it exposes one; ``None`` when unknown or not applicable (stores).
        provides (list[str]): The capability ids (``"family:kind"``) this service enables — empty for
            infra stores (they carry no pipeline capability).
        detail (str | None): Optional short note (e.g. why a sidecar is not reachable, or that a store
            is declared-not-probed).
    """

    model_config = ConfigDict(extra="forbid")

    name: str = Field(description="Stable service name (compose service / network alias).")
    role: str = Field(description="Short role label (e.g. 'vector', 'embed', 'parse-ocr').")
    reachable: bool = Field(
        description="Sidecar: /health probe currently passes. Store: configured (declared, not probed)."
    )
    device: str | None = Field(
        default=None,
        description="Device the sidecar reports at /health ('cuda'/'cpu'); None when unknown.",
    )
    provides: list[str] = Field(
        default_factory=list,
        description="Capability ids ('family:kind') this service enables (empty for infra stores).",
    )
    detail: str | None = Field(default=None, description="Optional short status note.")


class CapabilityMatrix(BaseModel):
    """
    The available pipeline kinds per family — 'what can this deployment do NOW'.

    Each list holds the SELECTABLE kinds of that family whose requirement is satisfied: in-worker or
    per-collection-key kinds are always listed; a sidecar-gated kind is listed only while its sidecar
    is reachable. ``metagen`` has no selectable provider kinds of its own (it delegates to the ``llm``
    family), so it is legitimately empty.

    Attributes:
        parsers (list[str]): Available ``parser`` kinds.
        ocr (list[str]): Available ``ocr`` kinds.
        embed (list[str]): Available ``embed`` kinds.
        chunkers (list[str]): Available ``chunker`` kinds.
        vlm (list[str]): Available ``vlm`` kinds.
        llm (list[str]): Available ``llm`` kinds.
        rerank (list[str]): Available ``rerank`` kinds.
        contextualize (list[str]): Available ``contextualize`` kinds.
        metagen (list[str]): Available ``metagen`` kinds (delegates to ``llm``; usually empty).
    """

    model_config = ConfigDict(extra="forbid")

    parsers: list[str] = Field(default_factory=list, description="Available parser kinds.")
    ocr: list[str] = Field(default_factory=list, description="Available ocr kinds.")
    embed: list[str] = Field(default_factory=list, description="Available embed kinds.")
    chunkers: list[str] = Field(default_factory=list, description="Available chunker kinds.")
    vlm: list[str] = Field(default_factory=list, description="Available vlm kinds.")
    llm: list[str] = Field(default_factory=list, description="Available llm kinds.")
    rerank: list[str] = Field(default_factory=list, description="Available rerank kinds.")
    contextualize: list[str] = Field(
        default_factory=list, description="Available contextualize kinds."
    )
    metagen: list[str] = Field(default_factory=list, description="Available metagen kinds.")


class CapabilitiesResponse(BaseModel):
    """
    The deployment capabilities snapshot returned by GET /capabilities.

    Attributes:
        version (str): The running app/image version (``FASTAPI_APP_VERSION``, falling back to the
            pinned ``DOCFORGE_TAG``).
        auth_enabled (bool): Whether API-key bearer auth gates ``/api/v1`` on this deployment.
        gpu_present (bool | None): True when any reachable sidecar reports device ``"cuda"``; False when
            reachable sidecars report only non-cuda devices; None when no device info is available.
        services (list[ServiceInfo]): The infra stores + optional sidecars, with reachability + what
            each unlocks.
        capabilities (CapabilityMatrix): The available pipeline kinds per family.
    """

    model_config = ConfigDict(extra="forbid")

    version: str = Field(
        description="Running app/image version (FASTAPI_APP_VERSION / DOCFORGE_TAG)."
    )
    auth_enabled: bool = Field(description="Whether API-key bearer auth gates /api/v1.")
    gpu_present: bool | None = Field(
        default=None,
        description="True if any reachable sidecar reports device 'cuda'; None when unknown.",
    )
    services: list[ServiceInfo] = Field(
        default_factory=list, description="Infra stores + optional sidecars."
    )
    capabilities: CapabilityMatrix = Field(description="Available pipeline kinds per family.")


__all__ = ["ServiceInfo", "CapabilityMatrix", "CapabilitiesResponse"]
