# ====== Code Summary ======
# Config of the MinerU2.5-Pro parser node — a NETWORK client, so its config is the per-collection
# endpoint (base_url + optional bearer + timeout). There is NO device knob: torch CPU/GPU is a
# deployment concern owned by the sidecar image (docs/architecture.md §4), and the MinerU sidecar's
# /parse endpoint takes no sub-pipeline query params (the backend/lang are sidecar-side env). The
# timeout defaults HIGH — MinerU2.5-Pro is a VLM (minutes per document, even on GPU), so the base
# 300 s would truncate a real multi-page parse.

# ====== Third-Party Library Imports ======
from pydantic import Field

# ====== Local Project Imports ======
from ..sidecar_base import SidecarParserConfig


class ParserMineruConfig(SidecarParserConfig):
    """MinerU2.5-Pro sidecar endpoint config.

    Timeout/retry come from ``TimeoutRetryConfig`` (``timeout_seconds`` overridden to 900 s — a VLM
    parse of a multi-page document is slow); retry runs through the shared ``NetworkRetry`` loop in the
    node.
    """

    base_url: str = Field(
        default="http://mineru_server:80",
        description="MinerU2.5-Pro sidecar endpoint. Defaults to the in-stack mineru_server so a parse "
        "chain escalation step added to a collection is reachable out of the box; override per "
        "collection to point at a remote sidecar.",
    )
    timeout_seconds: float = Field(
        default=900.0,
        gt=0,
        description="Per-request timeout (s). MinerU2.5-Pro is a VLM — minutes per document even on "
        "GPU, so the default is high; raise it further for long dense documents.",
    )


__all__ = ["ParserMineruConfig"]
