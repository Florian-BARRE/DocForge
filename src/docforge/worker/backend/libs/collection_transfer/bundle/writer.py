# ====== Code Summary ======
# BundleWriter — assembles a `.dcexport` bundle inside a temp working directory: it hands out
# streaming JSONL sinks (one per table), writes the content-addressed blob bytes ONE file per unique
# hash, records every data file's sha256 + size as it closes, and finally writes collection.json and
# the manifest.json (with the accumulated checksums). Nothing here uploads or tars — that is the
# archiver's job; this class only lays the tree down on disk, deterministically and streamed.

# ====== Standard Library Imports ======
from __future__ import annotations

import hashlib
import json
import pathlib
from typing import Any

# ====== Local Project Imports ======
from ..manifest import CollectionContractModel, ExportManifest, FileEntry
from ..paths import BundlePaths
from .sink import JsonlSink


class BundleWriter:
    """Lays out a `.dcexport` bundle tree in a working directory (streamed, checksummed)."""

    def __init__(self, work_dir: pathlib.Path) -> None:
        """
        Args:
            work_dir (pathlib.Path): The (empty) temp directory the bundle tree is built in.
        """
        self._root = work_dir
        self._root.mkdir(parents=True, exist_ok=True)
        (self._root / BundlePaths.BLOB_DIR).mkdir(parents=True, exist_ok=True)
        # rel_path -> FileEntry, accumulated as each data file closes.
        self._files: dict[str, FileEntry] = {}
        self._seen_blobs: set[str] = set()
        self.blob_count = 0

    @property
    def root(self) -> pathlib.Path:
        """The bundle working directory (the archiver tars this)."""
        return self._root

    def sink(self, rel_path: str) -> _TrackedSink:
        """Open a streaming JSONL sink for ``rel_path``; its checksum is recorded on close."""
        return _TrackedSink(self, rel_path, JsonlSink(self._root / rel_path))

    def write_blob(self, content_hash: str, data: bytes) -> bool:
        """
        Write a blob's raw bytes once (deduped by hash). Returns True if newly written.

        The file NAME is the content hash, so the bytes are self-verifying on import (re-hash ==
        name); the manifest therefore tracks blob COUNT, not per-blob checksum entries.
        """
        if content_hash in self._seen_blobs:
            return False
        self._seen_blobs.add(content_hash)
        (self._root / BundlePaths.blob_path(content_hash)).write_bytes(data)
        self.blob_count += 1
        return True

    def write_collection(self, contract: CollectionContractModel) -> None:
        """Write collection.json and record its checksum (a manifest-tracked data file)."""
        self._write_json(BundlePaths.COLLECTION, contract.model_dump(mode="json"))

    def write_manifest(self, manifest: ExportManifest) -> None:
        """Write manifest.json LAST, stamping in every accumulated file entry (self excluded)."""
        manifest.files = sorted(self._files.values(), key=lambda entry: entry.path)
        path = self._root / BundlePaths.MANIFEST
        path.write_text(manifest.model_dump_json(indent=2), encoding="utf-8")

    def _record(self, rel_path: str, sha256: str, size_bytes: int) -> None:
        """Register a closed data file's integrity entry for the manifest."""
        self._files[rel_path] = FileEntry(path=rel_path, sha256=sha256, size_bytes=size_bytes)

    def _write_json(self, rel_path: str, payload: dict[str, Any]) -> None:
        """Write a small JSON document and record its checksum (like a one-row sink)."""
        blob = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
        (self._root / rel_path).write_bytes(blob)
        self._record(rel_path, hashlib.sha256(blob).hexdigest(), len(blob))


class _TrackedSink:
    """A JsonlSink whose checksum is auto-registered on the parent writer at close."""

    def __init__(self, writer: BundleWriter, rel_path: str, sink: JsonlSink) -> None:
        self._writer = writer
        self._rel_path = rel_path
        self._sink = sink

    @property
    def rows(self) -> int:
        """How many rows have been written so far."""
        return self._sink.rows

    def write(self, row: dict[str, Any]) -> None:
        """Stream one row into the underlying sink."""
        self._sink.write(row)

    def __enter__(self) -> _TrackedSink:
        return self

    def __exit__(self, *_exc: object) -> None:
        sha256, size_bytes = self._sink.close()
        self._writer._record(self._rel_path, sha256, size_bytes)


__all__ = ["BundleWriter"]
