# ====== Code Summary ======
# The collection config-HISTORY resource — list a collection's config versions (who, when, what
# changed), read one (secrets masked), diff two, and restore one as a NEW version. All URL/query logic
# lives once in the pure _ConfigVersionsSpecs mixin so the async/sync shells differ ONLY by ``await``.

# ====== Local Project Imports ======
from .._requestspec import RequestSpec
from ..models.config_versions import (
    ConfigVersionDetail,
    ConfigVersionDiffResponse,
    ConfigVersionListResponse,
    ConfigVersionRestoreResponse,
)
from ._base import AsyncResource, SyncResource, _ResourceMixin


class _ConfigVersionsSpecs(_ResourceMixin):
    """Pure ``RequestSpec`` builders for the config-history endpoints."""

    @staticmethod
    def _base(collection_id: str) -> str:
        """The collection's ``/config-versions`` path."""
        return f"/collections/{collection_id}/config-versions"

    def _list_spec(self, collection_id: str, limit: int, offset: int) -> RequestSpec:
        """A GET of one newest-first page."""
        return RequestSpec(
            "GET", self._base(collection_id), params={"limit": limit, "offset": offset}
        )

    def _get_spec(self, collection_id: str, version: int) -> RequestSpec:
        """A GET of one masked snapshot."""
        return RequestSpec("GET", f"{self._base(collection_id)}/{version}")

    def _diff_spec(self, collection_id: str, from_version: int, to_version: int) -> RequestSpec:
        """A GET of the masked diff ``from_version`` → ``to_version``."""
        return RequestSpec(
            "GET",
            f"{self._base(collection_id)}/diff",
            params={"from": from_version, "to": to_version},
        )

    def _restore_spec(self, collection_id: str, version: int) -> RequestSpec:
        """A POST restoring ``version`` as a new version."""
        return RequestSpec("POST", f"{self._base(collection_id)}/{version}/restore")


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


class SyncConfigVersions(SyncResource, _ConfigVersionsSpecs):
    """Synchronous collection config history."""

    def list(
        self, collection_id: str, *, limit: int = 50, offset: int = 0
    ) -> ConfigVersionListResponse:
        """List a collection's config versions, newest first (see the async twin)."""
        return self._transport.request(
            self._list_spec(collection_id, limit, offset), ConfigVersionListResponse
        )

    def get(self, collection_id: str, version: int) -> ConfigVersionDetail:
        """Read one config version, secrets masked (see the async twin)."""
        return self._transport.request(self._get_spec(collection_id, version), ConfigVersionDetail)

    def diff(
        self, collection_id: str, from_version: int, to_version: int
    ) -> ConfigVersionDiffResponse:
        """Diff two config versions, secrets masked (see the async twin)."""
        return self._transport.request(
            self._diff_spec(collection_id, from_version, to_version), ConfigVersionDiffResponse
        )

    def restore(self, collection_id: str, version: int) -> ConfigVersionRestoreResponse:
        """Restore a config version as a NEW version (see the async twin)."""
        return self._transport.request(
            self._restore_spec(collection_id, version), ConfigVersionRestoreResponse
        )


__all__ = ["AsyncConfigVersions", "SyncConfigVersions"]
