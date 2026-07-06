# ====== Code Summary ======
# Config of the Gotenberg converter node — the service endpoint and the HTTP timeout. The URL goes
# through config like every provider endpoint (never hardcoded); conversions of big office files
# can be slow, hence the generous default timeout.

# ====== Third-Party Library Imports ======
from pydantic import Field

# ====== Internal Project Imports ======
from shared_libs.pipelines.base import NodeConfig


class ConverterGotenbergConfig(NodeConfig):
    """Gotenberg endpoint + HTTP behaviour."""

    base_url: str = Field(description="Gotenberg endpoint (e.g. http://gotenberg:3000).")
    timeout_seconds: float = Field(default=120.0, gt=0, description="HTTP timeout per conversion.")


__all__ = ["ConverterGotenbergConfig"]
