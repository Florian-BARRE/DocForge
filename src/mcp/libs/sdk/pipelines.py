# ====== Code Summary ======
# Pipelines sub-API: the read-only slice of the pipeline design surface under
# /api/v1/pipelines — discovery + the lean palette/blob payload. The advanced editing
# endpoints (inspect / edit / stages) require crafting a full GroupNodeBlob graph and are
# intentionally NOT wrapped here (they are a UI-editor concern, not a corpus-exploration one).

from __future__ import annotations

# ====== Standard Library Imports ======
from typing import Any

# ====== Third-Party Library Imports ======
from loggerplusplus import LoggerClass

# ====== Local Project Imports ======
from .transport import DocForgeTransport


class PipelinesApi(LoggerClass):
    """The pipeline design surface — discovery and the lean design payload (read-only)."""

    def __init__(self, transport: DocForgeTransport) -> None:
        """
        Bind the shared transport.

        Args:
            transport (DocForgeTransport): The shared HTTP transport.
        """
        LoggerClass.__init__(self)
        self._t = transport

    async def list_surfaces(self) -> Any:
        """Discover the available pipeline design surfaces (ingest / search) and their URLs."""
        return await self._t.get("/pipelines")

    async def get_design(self, key: str, full: bool = False) -> Any:
        """
        Open a pipeline design surface: palette + default blob + validation issues.

        Args:
            key (str): The pipeline key ("ingest" or "search").
            full (bool): When true, fill the advanced palette blocks (run_inputs, mechanics,
                artefacts).

        Returns:
            Any: PipelineDesignResponse — palette, blob, issues.
        """
        return await self._t.get(f"/pipelines/{key}", params={"full": full})
