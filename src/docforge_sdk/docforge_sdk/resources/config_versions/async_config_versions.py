# ====== Code Summary ======
# The asynchronous collection config history resource: the awaiting shell over the shared
# ``_ConfigVersionsSpecs`` builders.

# ====== Local Project Imports ======
from ...models.config_versions import (
    ConfigVersionDetail,
    ConfigVersionDiffResponse,
    ConfigVersionListResponse,
    ConfigVersionRestoreResponse,
)
from .._base import AsyncResource
from .specs import _ConfigVersionsSpecs


class AsyncConfigVersions(AsyncResource, _ConfigVersionsSpecs):
    """Asynchronous collection config history."""

    async def list(
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
        return await self._transport.request(
            self._list_spec(collection_id, limit, offset), ConfigVersionListResponse
        )

    async def get(self, collection_id: str, version: int) -> ConfigVersionDetail:
        """
        Read one config version (its {pipeline, search} snapshot, secrets masked).

        Args:
            collection_id (str): The collection's UUID.
            version (int): The version number.

        Returns:
            ConfigVersionDetail: The version metadata + masked snapshot.
        """
        return await self._transport.request(
            self._get_spec(collection_id, version), ConfigVersionDetail
        )

    async def diff(
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
        return await self._transport.request(
            self._diff_spec(collection_id, from_version, to_version), ConfigVersionDiffResponse
        )

    async def restore(self, collection_id: str, version: int) -> ConfigVersionRestoreResponse:
        """
        Restore a config version as a NEW version (current same-endpoint keys are kept).

        Args:
            collection_id (str): The collection's UUID.
            version (int): The version to re-apply.

        Returns:
            ConfigVersionRestoreResponse: The new version number + derived reindex flag.
        """
        return await self._transport.request(
            self._restore_spec(collection_id, version), ConfigVersionRestoreResponse
        )
