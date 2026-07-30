# ====== Code Summary ======
# The pipelines resource — discovery + design of the pipeline graph surfaces. The graph JSON is OPAQUE
# to the SDK: blob/operations/action pass through as plain dicts, only the typed ENVELOPE comes back.
# All URL/body logic lives once in the pure _PipelinesSpecs mixin so the async/sync shells differ ONLY
# by ``await``.

# ====== Standard Library Imports ======
from typing import Any

# ====== Local Project Imports ======
from .._requestspec import RequestSpec
from ..models.pipelines import (
    EditResponse,
    InspectResponse,
    PipelineDesignResponse,
    PipelineIndexResponse,
    StageApplyResponse,
    StageViewResponse,
)
from ._base import AsyncResource, SyncResource, _ResourceMixin


class _PipelinesSpecs(_ResourceMixin):
    """Pure ``RequestSpec`` builders for the pipeline endpoints — the single source of URL/body logic."""

    _PIPELINES_PATH = "/pipelines"

    def _list_surfaces_spec(self) -> RequestSpec:
        """
        Build the spec for discovering the available pipeline surfaces.

        Returns:
            RequestSpec: A GET on the pipelines index.
        """
        return RequestSpec("GET", self._PIPELINES_PATH)

    def _get_design_spec(self, key: str, full: bool) -> RequestSpec:
        """
        Build the spec for opening a pipeline's design payload.

        Args:
            key (str): The pipeline key (e.g. ``"ingest"``).
            full (bool): Whether to include the advanced palette blocks.

        Returns:
            RequestSpec: A GET on the pipeline resource, carrying the ``full`` query flag.
        """
        return RequestSpec("GET", f"{self._PIPELINES_PATH}/{key}", params={"full": full})

    def _inspect_spec(self, key: str, blob: dict[str, Any]) -> RequestSpec:
        """
        Build the spec for inspecting an edited pipeline blob.

        Args:
            key (str): The pipeline key.
            blob (dict[str, Any]): The opaque graph blob to inspect.

        Returns:
            RequestSpec: A POST to the pipeline's ``/inspect`` route.
        """
        return RequestSpec("POST", f"{self._PIPELINES_PATH}/{key}/inspect", json={"blob": blob})

    def _edit_spec(
        self, key: str, blob: dict[str, Any], operations: list[dict[str, Any]]
    ) -> RequestSpec:
        """
        Build the spec for applying graph operations to a pipeline blob.

        Args:
            key (str): The pipeline key.
            blob (dict[str, Any]): The opaque graph blob the operations start from.
            operations (list[dict[str, Any]]): The ordered, opaque edit operations.

        Returns:
            RequestSpec: A POST to the pipeline's ``/edit`` route.
        """
        return RequestSpec(
            "POST",
            f"{self._PIPELINES_PATH}/{key}/edit",
            json={"blob": blob, "operations": operations},
        )

    def _view_stages_spec(self, key: str, blob: dict[str, Any]) -> RequestSpec:
        """
        Build the spec for deriving the stage view of a pipeline blob.

        Args:
            key (str): The pipeline key.
            blob (dict[str, Any]): The opaque graph blob to view as stages.

        Returns:
            RequestSpec: A POST to the pipeline's ``/stages/view`` route.
        """
        return RequestSpec("POST", f"{self._PIPELINES_PATH}/{key}/stages/view", json={"blob": blob})

    def _apply_stage_spec(
        self, key: str, blob: dict[str, Any], action: dict[str, Any]
    ) -> RequestSpec:
        """
        Build the spec for compiling a stage action into a pipeline blob.

        Args:
            key (str): The pipeline key.
            blob (dict[str, Any]): The opaque graph blob the action starts from.
            action (dict[str, Any]): The opaque stage action to apply.

        Returns:
            RequestSpec: A POST to the pipeline's ``/stages/apply`` route.
        """
        return RequestSpec(
            "POST",
            f"{self._PIPELINES_PATH}/{key}/stages/apply",
            json={"blob": blob, "action": action},
        )


class AsyncPipelines(AsyncResource, _PipelinesSpecs):
    """Asynchronous pipeline discovery + design surface."""

    async def list_surfaces(self) -> PipelineIndexResponse:
        """
        Discover the pipeline design surfaces the backend serves.

        Returns:
            PipelineIndexResponse: One entry per available surface.
        """
        return await self._transport.request(self._list_surfaces_spec(), PipelineIndexResponse)

    async def get_design(self, key: str, full: bool = True) -> PipelineDesignResponse:
        """
        Open a pipeline's design payload (palette + blob + issues).

        Args:
            key (str): The pipeline key (e.g. ``"ingest"``).
            full (bool): Include the advanced palette blocks.

        Returns:
            PipelineDesignResponse: The design payload.
        """
        return await self._transport.request(
            self._get_design_spec(key, full), PipelineDesignResponse
        )

    async def inspect(self, key: str, blob: dict[str, Any]) -> InspectResponse:
        """
        Inspect an edited pipeline blob (validity + issues + described tree).

        Args:
            key (str): The pipeline key.
            blob (dict[str, Any]): The opaque graph blob to inspect.

        Returns:
            InspectResponse: The described mirror of the blob.
        """
        return await self._transport.request(self._inspect_spec(key, blob), InspectResponse)

    async def edit(
        self, key: str, blob: dict[str, Any], operations: list[dict[str, Any]]
    ) -> EditResponse:
        """
        Apply ordered graph operations to a pipeline blob, server-side.

        Args:
            key (str): The pipeline key.
            blob (dict[str, Any]): The opaque graph blob the operations start from.
            operations (list[dict[str, Any]]): The ordered, opaque edit operations.

        Returns:
            EditResponse: The edited blob plus validity + issues + described tree.
        """
        return await self._transport.request(
            self._edit_spec(key, blob, operations), EditResponse
        )

    async def view_stages(self, key: str, blob: dict[str, Any]) -> StageViewResponse:
        """
        Derive the stage view of a pipeline blob.

        Args:
            key (str): The pipeline key.
            blob (dict[str, Any]): The opaque graph blob to view as stages.

        Returns:
            StageViewResponse: The ordered stages plus the validity verdict.
        """
        return await self._transport.request(self._view_stages_spec(key, blob), StageViewResponse)

    async def apply_stage(
        self, key: str, blob: dict[str, Any], action: dict[str, Any]
    ) -> StageApplyResponse:
        """
        Compile a stage action into a pipeline blob.

        Args:
            key (str): The pipeline key.
            blob (dict[str, Any]): The opaque graph blob the action starts from.
            action (dict[str, Any]): The opaque stage action to apply.

        Returns:
            StageApplyResponse: The recompiled blob plus its stage view, validity and notices.
        """
        return await self._transport.request(
            self._apply_stage_spec(key, blob, action), StageApplyResponse
        )


class SyncPipelines(SyncResource, _PipelinesSpecs):
    """Synchronous pipeline discovery + design surface."""

    def list_surfaces(self) -> PipelineIndexResponse:
        """
        Discover the pipeline design surfaces the backend serves.

        Returns:
            PipelineIndexResponse: One entry per available surface.
        """
        return self._transport.request(self._list_surfaces_spec(), PipelineIndexResponse)

    def get_design(self, key: str, full: bool = True) -> PipelineDesignResponse:
        """
        Open a pipeline's design payload (palette + blob + issues).

        Args:
            key (str): The pipeline key (e.g. ``"ingest"``).
            full (bool): Include the advanced palette blocks.

        Returns:
            PipelineDesignResponse: The design payload.
        """
        return self._transport.request(self._get_design_spec(key, full), PipelineDesignResponse)

    def inspect(self, key: str, blob: dict[str, Any]) -> InspectResponse:
        """
        Inspect an edited pipeline blob (validity + issues + described tree).

        Args:
            key (str): The pipeline key.
            blob (dict[str, Any]): The opaque graph blob to inspect.

        Returns:
            InspectResponse: The described mirror of the blob.
        """
        return self._transport.request(self._inspect_spec(key, blob), InspectResponse)

    def edit(
        self, key: str, blob: dict[str, Any], operations: list[dict[str, Any]]
    ) -> EditResponse:
        """
        Apply ordered graph operations to a pipeline blob, server-side.

        Args:
            key (str): The pipeline key.
            blob (dict[str, Any]): The opaque graph blob the operations start from.
            operations (list[dict[str, Any]]): The ordered, opaque edit operations.

        Returns:
            EditResponse: The edited blob plus validity + issues + described tree.
        """
        return self._transport.request(self._edit_spec(key, blob, operations), EditResponse)

    def view_stages(self, key: str, blob: dict[str, Any]) -> StageViewResponse:
        """
        Derive the stage view of a pipeline blob.

        Args:
            key (str): The pipeline key.
            blob (dict[str, Any]): The opaque graph blob to view as stages.

        Returns:
            StageViewResponse: The ordered stages plus the validity verdict.
        """
        return self._transport.request(self._view_stages_spec(key, blob), StageViewResponse)

    def apply_stage(
        self, key: str, blob: dict[str, Any], action: dict[str, Any]
    ) -> StageApplyResponse:
        """
        Compile a stage action into a pipeline blob.

        Args:
            key (str): The pipeline key.
            blob (dict[str, Any]): The opaque graph blob the action starts from.
            action (dict[str, Any]): The opaque stage action to apply.

        Returns:
            StageApplyResponse: The recompiled blob plus its stage view, validity and notices.
        """
        return self._transport.request(
            self._apply_stage_spec(key, blob, action), StageApplyResponse
        )


__all__ = ["AsyncPipelines", "SyncPipelines"]
