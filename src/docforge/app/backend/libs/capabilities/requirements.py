# ====== Code Summary ======
# The SINGLE, well-commented place that knows which optional sidecar a pipeline kind needs, plus the
# family→registry mapping the capability matrix is built from. Every other module in this package
# derives from the tables here: the service inverts SIDECARS to gate kinds on sidecar reachability
# and to fill each service's ``provides`` list; the prober reads the sidecar URLs from RUNTIME_CONFIG
# by the ``config_attr`` named here. A pipeline kind that is NOT listed in a sidecar's ``provides`` is
# treated as always-available — it runs in-worker (docling, rapidocr, tesseract, the chunkers, granite_docling
# — GPU-preferred but still an in-worker node) OR it is a cloud provider keyed PER-COLLECTION (mistral
# ocr/llm, any openai-compatible endpoint): the deployment CAN do it, the credential arrives with the
# collection contract, so it is never gated on an in-stack sidecar.

# ====== Standard Library Imports ======
from dataclasses import dataclass

# ====== Third-Party Library Imports ======
from loggerplusplus import loggerplusplus


@dataclass(frozen=True)
class SidecarSpec:
    """
    One optional, in-stack sidecar service the deployment MAY run — probed for reachability.

    Attributes:
        name (str): Stable service name (matches the compose service / network alias).
        role (str): Short role label surfaced in the API (e.g. ``"embed"``, ``"parse-ocr"``).
        config_attr (str): The ``RUNTIME_CONFIG`` attribute holding this sidecar's ``/health`` base URL.
        provides (tuple[str, ...]): The capability ids (``"family:kind"``) this sidecar enables —
            those kinds are available ONLY while this sidecar is reachable.
    """

    name: str
    role: str
    config_attr: str
    provides: tuple[str, ...]


@dataclass(frozen=True)
class StoreSpec:
    """
    One always-present infrastructure store (never a pipeline capability, so no ``provides``).

    Its presence is derived from config (a configured URL/DSN), not a live probe — keeping the
    endpoint cheap and deterministic (the per-collection health endpoint owns real store round-trips).

    Attributes:
        name (str): Stable store name (compose service / network alias).
        role (str): Short role label surfaced in the API (e.g. ``"vector"``, ``"blob"``).
        config_attr (str): The ``RUNTIME_CONFIG`` attribute holding this store's URL/DSN.
    """

    name: str
    role: str
    config_attr: str


# The optional sidecars, each with the exact capability kinds it unlocks. This tuple is the ONE
# source of truth for "which sidecar does kind X need": the service inverts it (capability id →
# sidecar) to gate the matrix, and reads ``provides`` straight for each service row. bge_server hosts
# both dense/sparse embedding AND the cross-encoder reranker (TEI contract); paddle_server hosts the
# PP-Structure/PaddleOCR-VL parsers AND the per-figure paddle OCR reader.
SIDECARS: tuple[SidecarSpec, ...] = (
    SidecarSpec(
        name="gotenberg",
        role="convert",
        config_attr="CAPABILITIES_GOTENBERG_URL",
        provides=("converter:gotenberg",),
    ),
    SidecarSpec(
        name="bge_server",
        role="embed",
        config_attr="CAPABILITIES_BGE_SERVER_URL",
        provides=("embed:bge_server", "rerank:cross_encoder"),
    ),
    SidecarSpec(
        name="paddle_server",
        role="parse-ocr",
        config_attr="CAPABILITIES_PADDLE_SERVER_URL",
        provides=("parser:pp_structure", "parser:paddleocr_vl", "ocr:paddle"),
    ),
    SidecarSpec(
        name="mineru_server",
        role="parse",
        config_attr="CAPABILITIES_MINERU_SERVER_URL",
        provides=("parser:mineru",),
    ),
    SidecarSpec(
        name="dots_ocr_server",
        role="parse",
        config_attr="CAPABILITIES_DOTS_OCR_SERVER_URL",
        provides=("parser:dots_ocr",),
    ),
)

# The infra stores — always part of a running deployment; reported from config presence only.
STORES: tuple[StoreSpec, ...] = (
    StoreSpec(name="postgres", role="db", config_attr="POSTGRES_DSN"),
    StoreSpec(name="qdrant", role="vector", config_attr="QDRANT_URL"),
    StoreSpec(name="redis", role="queue", config_attr="REDIS_URL"),
    StoreSpec(name="seaweedfs", role="blob", config_attr="S3_ENDPOINT_URL"),
)

# The capability-matrix families: each response field maps to its NodeRegistry family. The kinds are
# read live from the registry palette (selectable nodes only), so a newly-registered provider shows
# up here with zero edits — only a NEW sidecar-gated kind needs a SIDECARS row above.
FAMILY_MAP: dict[str, str] = {
    "parsers": "parser",
    "ocr": "ocr",
    "embed": "embed",
    "chunkers": "chunker",
    "vlm": "vlm",
    "llm": "llm",
    "rerank": "rerank",
    "contextualize": "contextualize",
    "metagen": "metagen",
}

# Capability ids (``family:kind``) that run IN-WORKER (always available) or are CLOUD/per-collection
# (a base_url+key set on the collection, so the deployment can always OFFER them). These are NOT gated
# on an in-stack sidecar. Together with every ``SIDECARS.provides`` id, this set must COVER every
# selectable registry kind of the FAMILY_MAP families — the `tests/units/coherence` ratchet fails
# otherwise. That failure is the point: a newly-added provider kind forces an explicit decision here
# (in-worker/cloud → add it below; sidecar-hosted → add a SIDECARS row) instead of silently defaulting
# to "always available" (which would wrongly advertise a sidecar-hosted kind even when its sidecar is
# down). Ratchet > prose.
IN_WORKER_OR_CLOUD: frozenset[str] = frozenset(
    {
        # parsers — docling (in-worker default) + granite_docling (in-worker VLM, GPU-preferred)
        "parser:docling",
        "parser:granite_docling",
        # ocr — rapidocr/tesseract in-worker; mistral is a cloud/per-collection API
        "ocr:rapidocr",
        "ocr:tesseract",
        "ocr:mistral",
        # embed / vlm / llm — the OpenAI-compatible + mistral providers are cloud/per-collection
        "embed:openai_compatible",
        "vlm:openai_compatible",
        "llm:openai_compatible",
        "llm:mistral",
        # chunkers — all in-worker
        "chunker:fixed_size",
        "chunker:semantic",
        "chunker:structure_aware",
        # contextualize — breadcrumb/sliding/doc_meta in-worker; llm is cloud/per-collection
        "contextualize:breadcrumb",
        "contextualize:sliding",
        "contextualize:doc_meta",
        "contextualize:llm",
    }
)


class CapabilityRequirements:
    """Static-only accessor over the requirement tables — never instantiated."""

    logger = loggerplusplus.bind(identifier="CapabilityRequirements")

    def __new__(cls, *args: object, **kwargs: object) -> None:
        raise TypeError("CapabilityRequirements is a static-only class and cannot be instantiated.")

    @classmethod
    def sidecar_by_capability(cls) -> dict[str, str]:
        """
        Invert ``SIDECARS`` into ``capability id → sidecar name`` — the matrix gating lookup.

        Returns:
            dict[str, str]: Every sidecar-gated capability id mapped to the sidecar that hosts it.
        """
        # 1. One entry per (sidecar, capability) pair — the flat reverse index of SIDECARS.provides.
        return {capability: sidecar.name for sidecar in SIDECARS for capability in sidecar.provides}

    @classmethod
    def is_available(cls, capability_id: str, reachable_sidecars: set[str]) -> bool:
        """
        Decide whether a capability kind is usable in THIS deployment right now.

        Args:
            capability_id (str): The ``"family:kind"`` id to test.
            reachable_sidecars (set[str]): The sidecar names whose ``/health`` probe currently passes.

        Returns:
            bool: True when the kind is in-worker / per-collection-key (always available), or when its
            hosting sidecar is currently reachable.
        """
        # 1. A sidecar-gated kind is available only while its sidecar answers; everything else
        #    (in-worker or per-collection cloud key) is always available.
        required = cls.sidecar_by_capability().get(capability_id)
        if required is None:
            return True
        return required in reachable_sidecars


__all__ = [
    "SidecarSpec",
    "StoreSpec",
    "SIDECARS",
    "STORES",
    "FAMILY_MAP",
    "CapabilityRequirements",
]
