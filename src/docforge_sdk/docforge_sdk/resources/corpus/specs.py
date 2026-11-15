# ====== Code Summary ======
# The corpus resource — the server-side document GRID and its bulk operations. `query` returns one
# filtered/sorted/paginated page of a collection's documents; the three bulk ops (`bulk_delete`,
# `bulk_set_enabled`, `bulk_reingest`) each take the ONE shared DocumentSelector (an explicit id set
# XOR a filter minus a few deselected ids), so "act on all 100k matching, minus 3" needs no client-side
# id enumeration. All URL/body logic lives once in the pure _CorpusSpecs mixin; the async/sync shells
# differ only by ``await``.

# ====== Local Project Imports ======
from ..._requestspec import RequestSpec
from ...models.corpus import (
    DocumentQueryRequest,
    DocumentSelector,
)
from .._base import _ResourceMixin


class _CorpusSpecs(_ResourceMixin):
    """Pure ``RequestSpec`` builders for the corpus grid + bulk-op endpoints."""

    _COLLECTIONS_PATH = "/collections"

    def _docs_path(self, collection_id: str, action: str) -> str:
        """The path to a collection's documents sub-action (query / delete / set-enabled / reingest)."""
        return f"{self._COLLECTIONS_PATH}/{collection_id}/documents/{action}"

    def _query_spec(self, collection_id: str, request: DocumentQueryRequest) -> RequestSpec:
        """A POST carrying the filter/sort/pagination body → one page of grid rows."""
        return RequestSpec(
            "POST", self._docs_path(collection_id, "query"), json=request.model_dump(mode="json")
        )

    def _bulk_delete_spec(self, collection_id: str, selector: DocumentSelector) -> RequestSpec:
        """A POST carrying the selector → a bulk delete."""
        return RequestSpec(
            "POST", self._docs_path(collection_id, "delete"), json=selector.model_dump(mode="json")
        )

    def _bulk_set_enabled_spec(
        self, collection_id: str, selector: DocumentSelector, enabled: bool
    ) -> RequestSpec:
        """A POST carrying the selector (+ ``enabled`` query param) → a bulk enable/disable."""
        return RequestSpec(
            "POST",
            self._docs_path(collection_id, "set-enabled"),
            params={"enabled": enabled},
            json=selector.model_dump(mode="json"),
        )

    def _bulk_reingest_spec(
        self,
        collection_id: str,
        selector: DocumentSelector,
        force: bool,
        replay_from: str | None,
        confirm_estimate: bool,
    ) -> RequestSpec:
        """A POST carrying the selector (+ force/replay_from/confirm_estimate query params)."""
        params: dict[str, object] = {"force": force, "confirm_estimate": confirm_estimate}
        if replay_from is not None:
            params["replay_from"] = replay_from
        return RequestSpec(
            "POST",
            self._docs_path(collection_id, "reingest"),
            params=params,
            json=selector.model_dump(mode="json"),
        )
