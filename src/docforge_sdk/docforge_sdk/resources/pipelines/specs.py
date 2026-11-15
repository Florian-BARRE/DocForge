# ====== Code Summary ======
# The pipelines resource — discovery + design of the pipeline graph surfaces. The graph JSON is OPAQUE
# to the SDK: blob/operations/action pass through as plain dicts, only the typed ENVELOPE comes back.
# All URL/body logic lives once in the pure _PipelinesSpecs mixin so the async/sync shells differ ONLY
# by ``await``.

# ====== Standard Library Imports ======
from typing import Any

# ====== Local Project Imports ======
from ..._requestspec import RequestSpec
from .._base import _ResourceMixin


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

    def _apply_collection_stage_spec(
        self, collection_id: str, action: dict[str, Any], note: str | None
    ) -> RequestSpec:
        """
        Build the spec for applying a stage action to a collection's STORED pipeline (persisted).

        Args:
            collection_id (str): The collection whose pipeline is edited.
            action (dict[str, Any]): The opaque stage action to apply.
            note (str | None): Optional note stored on the config-version snapshot.

        Returns:
            RequestSpec: A POST to the collection's ``/pipeline/stages/apply`` route.
        """
        body: dict[str, Any] = {"action": action}
        if note is not None:
            body["note"] = note
        return RequestSpec("POST", f"/collections/{collection_id}/pipeline/stages/apply", json=body)
