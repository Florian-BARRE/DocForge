# ====== Code Summary ======
# The documents resource: multipart upload (admission) and the searchability toggle. Upload routes
# through the transport's multipart helper; the toggle is a plain PATCH. All URL/body/multipart logic
# lives once in the pure _DocumentsSpecs mixin so the async/sync shells differ ONLY by ``await``.

# ====== Standard Library Imports ======
import json
from pathlib import Path
from typing import Any

# ====== Local Project Imports ======
from ..._requestspec import RequestSpec
from ...models.documents import (
    EnabledPatch,
    MetadataValuesPatch,
)
from .._base import _ResourceMixin


class _DocumentsSpecs(_ResourceMixin):
    """Pure request builders for the documents endpoints — the single source of URL/body/multipart logic."""

    _DOCUMENTS_PATH = "/documents"

    @staticmethod
    def _upload_parts(
        collection_id: str,
        file: str | Path | bytes,
        metadata: dict[str, Any] | None,
        filename: str | None,
    ) -> tuple[dict[str, Any], dict[str, str]]:
        """
        Build the multipart ``files`` and ``data`` parts of an upload from a path or raw bytes.

        Args:
            collection_id (str): The target collection's UUID.
            file (str | Path | bytes): A local file path or the raw bytes to ingest.
            metadata (dict[str, Any] | None): Declared metadata; serialised to the JSON form field.
            filename (str | None): Override name; defaults to the path's name, else ``"upload"``.

        Returns:
            tuple[dict[str, Any], dict[str, str]]: The httpx ``files`` mapping and the form ``data``.
        """
        # 1. Resolve raw bytes + a filename from either a local path or in-memory bytes.
        if isinstance(file, bytes):
            content, resolved_name = file, (filename or "upload")
        else:
            path = Path(file)
            content, resolved_name = path.read_bytes(), (filename or path.name)

        # 2. Assemble the multipart file part and the accompanying form fields.
        files = {"file": (resolved_name, content)}
        data = {"collection_id": collection_id, "metadata": json.dumps(metadata or {})}
        return files, data

    def _set_enabled_spec(self, document_id: str, enabled: bool) -> RequestSpec:
        """
        Build the spec for toggling a document's searchability.

        Args:
            document_id (str): The document to toggle.
            enabled (bool): The desired searchability state.

        Returns:
            RequestSpec: A PATCH on the document's ``/enabled`` sub-resource.
        """
        return RequestSpec(
            "PATCH",
            f"{self._DOCUMENTS_PATH}/{document_id}/enabled",
            json=EnabledPatch(enabled=enabled).model_dump(mode="json"),
        )

    def _update_metadata_spec(self, document_id: str, values: dict[str, Any]) -> RequestSpec:
        """A PATCH writing metadata VALUES (document-scope fields) onto one document in place."""
        return RequestSpec(
            "PATCH",
            f"{self._DOCUMENTS_PATH}/{document_id}/metadata",
            json=MetadataValuesPatch(values=values).model_dump(mode="json"),
        )

    def _reingest_spec(self, document_id: str, force: bool, replay_from: str | None) -> RequestSpec:
        """A POST re-running one document (``force`` bypasses the cache, ``replay_from`` skips parse)."""
        params: dict[str, object] = {"force": force}
        if replay_from is not None:
            params["replay_from"] = replay_from
        return RequestSpec("POST", f"{self._DOCUMENTS_PATH}/{document_id}/reingest", params=params)

    def _purge_trace_payloads_spec(self, document_id: str) -> RequestSpec:
        """A POST reclaiming one document's stored full execution-trace payloads (best-effort)."""
        return RequestSpec("POST", f"{self._DOCUMENTS_PATH}/{document_id}/trace-payloads/purge")

    def _markdown_path(self, document_id: str) -> str:
        """
        Build the API-relative path to a document's on-the-fly markdown view.

        Args:
            document_id (str): The document to render.

        Returns:
            str: The path to the document's ``/markdown`` sub-resource.
        """
        return f"{self._DOCUMENTS_PATH}/{document_id}/markdown"

    def _html_path(self, document_id: str) -> str:
        """
        Build the API-relative path to a document's on-the-fly HTML view.

        Args:
            document_id (str): The document to render.

        Returns:
            str: The path to the document's ``/html`` sub-resource.
        """
        return f"{self._DOCUMENTS_PATH}/{document_id}/html"
