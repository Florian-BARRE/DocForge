# ====== Code Summary ======
# GENERATED FILE — DO NOT EDIT. Derived from async_pipelines.py by scripts/generate_sync.py;
# regenerate with `uv run --frozen python scripts/generate_sync.py` from src/docforge_sdk
# (tests/unit/test_sync_codegen.py fails when this file drifts from its async source).
# The synchronous pipeline discovery + design surface resource: the blocking shell over the shared
# ``_PipelinesSpecs`` builders.

# ====== Standard Library Imports ======
from typing import Any

# ====== Local Project Imports ======
from ...models.pipelines import (
    CollectionStageApplyResponse,
    EditResponse,
    InspectResponse,
    PipelineDesignResponse,
    PipelineIndexResponse,
    StageApplyResponse,
    StageViewResponse,
)
from .._base import SyncResource
from .specs import _PipelinesSpecs


class SyncPipelines(SyncResource, _PipelinesSpecs):
    """Synchronous pipeline discovery + design surface."""

    def list_surfaces(self) -> PipelineIndexResponse:
        """
        Discover the pipeline design surfaces the backend serves.

        Returns:
            PipelineIndexResponse: One entry per available surface.
        """
        return self._transport.request(self._list_surfaces_spec(), PipelineIndexResponse)

    def get_design(self, key: str, full: bool = False) -> PipelineDesignResponse:
        """
        Open a pipeline's design payload (palette + blob + issues).

        Args:
            key (str): The pipeline key (e.g. ``"ingest"``).
            full (bool): Include the advanced palette blocks. Defaults to False (the lean palette),
                matching the server's ``?full`` default.

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

    def apply_collection_stage(
        self, collection_id: str, action: dict[str, Any], note: str | None = None
    ) -> CollectionStageApplyResponse:
        """
        Apply one stage action to a collection's stored pipeline and persist a valid result.

        Prefer ``{"action": "set_config", "mode": "merge", ...}`` for single-key edits: every other
        key, secrets included, is kept. Nothing is written when the result is invalid or a no-op.

        Args:
            collection_id (str): The collection whose pipeline is edited.
            action (dict[str, Any]): The opaque stage action to apply.
            note (str | None): Optional note stored on the config-version snapshot.

        Returns:
            CollectionStageApplyResponse: The redacted stage view, validity, notices and whether
            the change was persisted.
        """
        return self._transport.request(
            self._apply_collection_stage_spec(collection_id, action, note),
            CollectionStageApplyResponse,
        )
