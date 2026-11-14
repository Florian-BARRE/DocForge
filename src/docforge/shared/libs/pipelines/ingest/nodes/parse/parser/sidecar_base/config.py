# ====== Code Summary ======
# SidecarParserConfig — the config every sidecar parser node shares. A sidecar parser is a NETWORK
# client, so its config is the per-collection endpoint (base_url + optional bearer + timeout). There
# is NO device knob: torch/Paddle CPU/GPU is a deployment concern owned by the sidecar image
# (docs/architecture.md §4). Each engine re-declares ``base_url`` (its in-stack default) and
# ``timeout_seconds`` (its own slowness) and adds its sub-pipeline toggles, if any.

# ====== Third-Party Library Imports ======
from pydantic import Field, field_validator

# ====== Internal Project Imports ======
from shared_libs.pipelines.base import TimeoutRetryConfig


class SidecarParserConfig(TimeoutRetryConfig):
    """Endpoint config shared by the sidecar parsers.

    Timeout/retry come from ``TimeoutRetryConfig``; retry runs through the shared ``NetworkRetry``
    loop in the node. Subclasses override ``base_url`` and ``timeout_seconds`` with their defaults.
    """

    base_url: str = Field(description="Sidecar endpoint.")
    api_key: str = Field(default="", description="Bearer token when the sidecar requires one.")

    @field_validator("base_url", mode="before")
    @classmethod
    def _strip_whitespace(cls, value: object) -> object:
        """Strip pasted whitespace — a trailing newline breaks the HTTP request line."""
        return value.strip() if isinstance(value, str) else value


__all__ = ["SidecarParserConfig"]
