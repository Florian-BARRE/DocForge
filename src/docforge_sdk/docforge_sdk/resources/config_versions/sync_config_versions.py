# ====== Code Summary ======
# GENERATED FILE — DO NOT EDIT. Derived from async_config_versions.py by scripts/generate_sync.py;
# regenerate with `uv run --frozen python scripts/generate_sync.py` from src/docforge_sdk
# (tests/unit/test_sync_codegen.py fails when this file drifts from its async source).
# The synchronous collection config history resource: the blocking shell over the shared
# ``_ConfigVersionsSpecs`` builders.

# ====== Local Project Imports ======
from ...models.config_versions import (
    ConfigVersionDetail,
    ConfigVersionDiffResponse,
    ConfigVersionListResponse,
    ConfigVersionRestoreResponse,
)
from .._base import SyncResource
from .specs import _ConfigVersionsSpecs


class SyncConfigVersions(SyncResource, _ConfigVersionsSpecs):
    """Synchronous collection config history."""

    def list(
        self, collection_id: str, *, limit: int = 50, offset: int = 0
    ) -> ConfigVersionListResponse:
        """
        List a collection's config versions, newest first, with author and change summary.

        Args:
            collection_id (str): The collection's UUID.
            limit (int): Page size (1–200).
            offset (int): Newer versions to skip.

        Returns:
            ConfigVersionListResponse: The page + total.
        """
        return self._transport.request(
            self._list_spec(collection_id, limit, offset), ConfigVersionListResponse
        )

    def get(self, collection_id: str, version: int) -> ConfigVersionDetail:
        """
        Read one config version (its {pipeline, search} snapshot, secrets masked).

        Args:
            collection_id (str): The collection's UUID.
            version (int): The version number.

        Returns:
            ConfigVersionDetail: The version metadata + masked snapshot.
        """
        return self._transport.request(self._get_spec(collection_id, version), ConfigVersionDetail)

    def diff(
        self, collection_id: str, from_version: int, to_version: int
    ) -> ConfigVersionDiffResponse:
        """
        Diff two config versions (added / removed / changed paths, secrets masked).

        Args:
            collection_id (str): The collection's UUID.
            from_version (int): The base version.
            to_version (int): The compared version.

        Returns:
            ConfigVersionDiffResponse: The structured diff.
        """
        return self._transport.request(
            self._diff_spec(collection_id, from_version, to_version), ConfigVersionDiffResponse
        )

    def restore(self, collection_id: str, version: int) -> ConfigVersionRestoreResponse:
        """
        Restore a config version as a NEW version (current same-endpoint keys are kept).

        Args:
            collection_id (str): The collection's UUID.
            version (int): The version to re-apply.

        Returns:
            ConfigVersionRestoreResponse: The new version number + derived reindex flag.
        """
        return self._transport.request(
            self._restore_spec(collection_id, version), ConfigVersionRestoreResponse
        )
