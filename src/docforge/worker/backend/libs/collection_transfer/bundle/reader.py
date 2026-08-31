# ====== Code Summary ======
# BundleReader — the read side of an extracted `.dcexport` tree. It loads and validates the manifest
# + collection contract, verifies every data file's sha256 against the manifest BEFORE any row is
# streamed (a tampered/truncated bundle fails fast, before a single write), then hands out streaming
# JSONL iterators (one row at a time, never a whole table in memory) and content-verified blob bytes
# (re-hash == filename). Validation and reads are separate so the importer can gate on validate()
# once, up front, then stream.

# ====== Standard Library Imports ======
from __future__ import annotations

import hashlib
import json
import pathlib
from collections.abc import Iterator
from typing import Any

# ====== Local Project Imports ======
from ..manifest import CollectionContractModel, ExportManifest, is_supported_version
from ..paths import BundlePaths


class BundleValidationError(Exception):
    """Raised when a bundle is unreadable, unsupported, or fails a checksum — never a partial import."""


class BundleReader:
    """Reads + validates an extracted bundle tree, then streams its rows and blob bytes."""

    def __init__(self, root: pathlib.Path) -> None:
        """
        Args:
            root (pathlib.Path): The directory the bundle tar was extracted into.
        """
        self._root = root
        self._manifest: ExportManifest | None = None

    @property
    def manifest(self) -> ExportManifest:
        """The parsed manifest (call ``validate`` first)."""
        if self._manifest is None:
            raise BundleValidationError("manifest not loaded — call validate() first")
        return self._manifest

    def validate(self) -> ExportManifest:
        """
        Load the manifest, gate the format version, and verify every data file's sha256.

        Returns:
            ExportManifest: The validated manifest.

        Raises:
            BundleValidationError: On a missing/malformed manifest, an unsupported format version,
                a missing dense_dim, or any per-file checksum mismatch.
        """
        # 1. The manifest must exist, parse and be a version this build understands.
        manifest_path = self._root / BundlePaths.MANIFEST
        if not manifest_path.exists():
            raise BundleValidationError("bundle has no manifest.json")
        try:
            manifest = ExportManifest.model_validate_json(manifest_path.read_text("utf-8"))
        except Exception as exc:  # noqa: BLE001 — any parse/validation error is a bad bundle
            raise BundleValidationError(f"manifest.json is invalid: {exc}") from exc
        if not is_supported_version(manifest.format_version):
            raise BundleValidationError(
                f"unsupported bundle format_version {manifest.format_version}"
            )
        if manifest.counts.points > 0 and manifest.dense_dim <= 0:
            raise BundleValidationError(
                "manifest carries points but no positive dense_dim to recreate the vector space"
            )

        # 2. Every listed data file must be present and match its recorded checksum.
        for entry in manifest.files:
            path = self._root / entry.path
            if not path.exists():
                raise BundleValidationError(f"bundle is missing file {entry.path}")
            digest = self._sha256_file(path)
            if digest != entry.sha256:
                raise BundleValidationError(
                    f"checksum mismatch for {entry.path}: expected {entry.sha256}, got {digest}"
                )
        self._manifest = manifest
        return manifest

    def read_collection(self) -> CollectionContractModel:
        """Parse collection.json into its typed contract model."""
        path = self._root / BundlePaths.COLLECTION
        if not path.exists():
            raise BundleValidationError("bundle has no collection.json")
        return CollectionContractModel.model_validate_json(path.read_text("utf-8"))

    def iter_rows(self, rel_path: str) -> Iterator[dict[str, Any]]:
        """Stream a JSONL data file row by row (absent file → no rows)."""
        path = self._root / rel_path
        if not path.exists():
            return
        with path.open("r", encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if line:
                    yield json.loads(line)

    def read_blob(self, content_hash: str) -> bytes:
        """Read a blob's bytes, verifying the content address (re-hash == filename)."""
        path = self._root / BundlePaths.blob_path(content_hash)
        if not path.exists():
            raise BundleValidationError(f"bundle is missing blob {content_hash}")
        data = path.read_bytes()
        digest = hashlib.sha256(data).hexdigest()
        if digest != content_hash:
            raise BundleValidationError(
                f"blob content-address mismatch: file {content_hash} hashes to {digest}"
            )
        return data

    @staticmethod
    def _sha256_file(path: pathlib.Path) -> str:
        """Compute a file's sha256 in bounded chunks (never load the whole file)."""
        hasher = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                hasher.update(chunk)
        return hasher.hexdigest()


__all__ = ["BundleReader", "BundleValidationError"]
