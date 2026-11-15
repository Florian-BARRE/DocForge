# ====== Code Summary ======
# The collection config-HISTORY resource — list a collection's config versions (who, when, what
# changed), read one (secrets masked), diff two, and restore one as a NEW version. All URL/query logic
# lives once in the pure _ConfigVersionsSpecs mixin so the async/sync shells differ ONLY by ``await``.

# ====== Local Project Imports ======
from ..._requestspec import RequestSpec
from .._base import _ResourceMixin


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
