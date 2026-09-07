# ====== Code Summary ======
# Config of the dots.ocr parser node — a NETWORK client, so its config is the per-collection endpoint
# (base_url + optional bearer + timeout). There is NO device knob: torch/CUDA CPU/GPU is a deployment
# concern owned by the sidecar image (invariant #7), and the dots_ocr sidecar's /parse endpoint takes
# no sub-pipeline query params (rendering DPI/backend are sidecar-side env). The timeout defaults HIGH —
# dots.ocr is a per-page VLM (minutes per document, even on GPU), so the base 300 s would truncate a
# real multi-page parse.

# ====== Third-Party Library Imports ======
from pydantic import Field, field_validator

# ====== Internal Project Imports ======
from shared_libs.pipelines.base import TimeoutRetryConfig


class ParserDotsOcrConfig(TimeoutRetryConfig):
    """dots.ocr sidecar endpoint config.

    Timeout/retry come from ``TimeoutRetryConfig`` (``timeout_seconds`` overridden to 900 s — a
    per-page VLM parse of a multi-page document is slow); retry runs through the shared ``NetworkRetry``
    loop in the node.
    """

    base_url: str = Field(
        default="http://dots_ocr_server:80",
        description="dots.ocr sidecar endpoint. Defaults to the in-stack dots_ocr_server so a parse "
        "chain escalation step added to a collection is reachable out of the box; override per "
        "collection to point at a remote sidecar.",
    )
    api_key: str = Field(default="", description="Bearer token when the sidecar requires one.")
    timeout_seconds: float = Field(
        default=900.0,
        gt=0,
        description="Per-request timeout (s). dots.ocr is a per-page VLM — minutes per document even "
        "on GPU, so the default is high; raise it further for long dense documents.",
    )

    @field_validator("base_url", mode="before")
    @classmethod
    def _strip_whitespace(cls, value: object) -> object:
        """Strip pasted whitespace — a trailing newline breaks the HTTP request line."""
        return value.strip() if isinstance(value, str) else value


__all__ = ["ParserDotsOcrConfig"]
