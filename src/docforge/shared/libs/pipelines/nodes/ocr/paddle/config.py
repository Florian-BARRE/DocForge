# ====== Code Summary ======
# Config of the PaddleOCR node — a NETWORK client of the in-stack paddle_server sidecar's OCR-only
# endpoint. Its config is the per-collection endpoint (base_url + optional bearer + timeout/retry).
# There is NO device knob: PaddlePaddle CPU/GPU is a deployment concern owned by the sidecar image
# (invariant #7). base_url defaults to the in-stack sidecar so the provider is reachable out of the
# box; override per collection to point at a remote sidecar.

# ====== Third-Party Library Imports ======
from pydantic import Field, field_validator

# ====== Internal Project Imports ======
from shared_libs.pipelines.base import TimeoutRetryConfig

# ====== Local Project Imports ======
from ..base import BaseOcrConfig


class OcrPaddleConfig(BaseOcrConfig, TimeoutRetryConfig):
    """PaddleOCR sidecar endpoint (OCR-only) + per-collection timeout/retry.

    Mixes the shared network timeout/retry surface (``TimeoutRetryConfig``) onto the empty OCR base:
    the escalation threshold lives on the graph (a ``ScoreBelow`` transition), never in the config.
    Retry runs through the shared ``NetworkRetry`` loop in the node.
    """

    base_url: str = Field(
        default="http://paddle_server:80",
        description="PaddleOCR sidecar endpoint. Defaults to the in-stack sidecar so the provider "
        "is reachable out of the box; override per collection to point at a remote sidecar.",
    )
    api_key: str = Field(default="", description="Bearer token when the sidecar requires one.")

    @field_validator("base_url", mode="before")
    @classmethod
    def _strip_whitespace(cls, value: object) -> object:
        """Strip pasted whitespace — a trailing newline breaks the HTTP request line."""
        return value.strip() if isinstance(value, str) else value


__all__ = ["OcrPaddleConfig"]
