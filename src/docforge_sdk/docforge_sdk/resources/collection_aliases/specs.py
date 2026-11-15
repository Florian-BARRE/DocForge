# ====== Code Summary ======
# The collection-alias resource — list the aliases (name → current target), create or atomically
# re-point one (the "switch": every key scoped `alias:<name>` and every client addressing the alias
# follow it on the next request), and delete one. URL logic lives once in the pure
# _CollectionAliasesSpecs mixin so the async/sync shells differ ONLY by ``await``.

# ====== Local Project Imports ======
from ..._requestspec import RequestSpec
from ...models.collection_aliases import (
    SetCollectionAliasRequest,
)
from .._base import _ResourceMixin


class _CollectionAliasesSpecs(_ResourceMixin):
    """Pure ``RequestSpec`` builders for the collection-alias endpoints."""

    _BASE = "/collection-aliases"

    def _list_spec(self) -> RequestSpec:
        """A GET of every alias the caller may see."""
        return RequestSpec("GET", self._BASE)

    def _set_spec(self, name: str, collection_id: str) -> RequestSpec:
        """A PUT creating / re-pointing ``name`` to ``collection_id``."""
        body = SetCollectionAliasRequest(collection_id=collection_id)
        return RequestSpec("PUT", f"{self._BASE}/{name}", json=body.model_dump(mode="json"))

    def _delete_spec(self, name: str) -> RequestSpec:
        """A DELETE of one alias."""
        return RequestSpec("DELETE", f"{self._BASE}/{name}")
