# ====== Code Summary ======
# BundleArchive — the tar (de)serialization of a bundle working directory, with optional zstd
# compression. Packing streams the whole tree into a single `.dcexport` file (``w|`` streaming mode,
# never the random-access ``w:`` that buffers), optionally through a zstd stream writer; unpacking
# reverses it, hardening extraction against path traversal so a hostile bundle can never write
# outside the target directory. The compression choice travels in the manifest, but the reader
# sniffs the zstd magic so a bundle opens regardless of a caller-declared codec.

# ====== Standard Library Imports ======
from __future__ import annotations

import pathlib
import tarfile

# ====== Third-Party Library Imports ======
import zstandard

# The zstd frame magic number (little-endian) — used to sniff a compressed bundle on open.
_ZSTD_MAGIC = b"\x28\xb5\x2f\xfd"

COMPRESSION_NONE = "none"
COMPRESSION_ZSTD = "zstd"


class BundleArchive:
    """Pack a bundle working directory into a `.dcexport` tar (optionally zstd) and back."""

    def __new__(cls, *args: object, **kwargs: object) -> None:
        raise TypeError("BundleArchive is a static-only class and cannot be instantiated.")

    @staticmethod
    def pack(work_dir: pathlib.Path, out_path: pathlib.Path, compression: str) -> None:
        """
        Stream a bundle tree into a single tar file, optionally zstd-compressed.

        Args:
            work_dir (pathlib.Path): The assembled bundle root (contains manifest.json et al.).
            out_path (pathlib.Path): The `.dcexport` file to create.
            compression (str): ``"none"`` or ``"zstd"``.
        """
        if compression == COMPRESSION_ZSTD:
            compressor = zstandard.ZstdCompressor(level=10)
            with out_path.open("wb") as raw, compressor.stream_writer(raw) as stream:
                with tarfile.open(fileobj=stream, mode="w|") as tar:
                    tar.add(work_dir, arcname=".")
            return
        with tarfile.open(out_path, mode="w") as tar:
            tar.add(work_dir, arcname=".")

    @staticmethod
    def unpack(archive_path: pathlib.Path, dest_dir: pathlib.Path) -> None:
        """
        Extract a `.dcexport` tar (auto-detecting zstd) into ``dest_dir``, safely.

        Args:
            archive_path (pathlib.Path): The bundle file to extract.
            dest_dir (pathlib.Path): The (existing) directory to extract into.
        """
        if BundleArchive._is_zstd(archive_path):
            decompressor = zstandard.ZstdDecompressor()
            with archive_path.open("rb") as raw, decompressor.stream_reader(raw) as stream:
                with tarfile.open(fileobj=stream, mode="r|") as tar:
                    BundleArchive._safe_extract(tar, dest_dir)
            return
        with tarfile.open(archive_path, mode="r:*") as tar:
            BundleArchive._safe_extract(tar, dest_dir)

    @staticmethod
    def _is_zstd(archive_path: pathlib.Path) -> bool:
        """Sniff the zstd frame magic so the reader is codec-agnostic."""
        with archive_path.open("rb") as handle:
            return handle.read(4) == _ZSTD_MAGIC

    @staticmethod
    def _safe_extract(tar: tarfile.TarFile, dest_dir: pathlib.Path) -> None:
        """Extract every member, rejecting any path that escapes ``dest_dir`` (traversal guard)."""
        dest = dest_dir.resolve()
        for member in tar:
            target = (dest / member.name).resolve()
            if not (target == dest or dest in target.parents):
                raise ValueError(f"bundle member escapes extraction root: {member.name}")
            tar.extract(member, dest_dir, filter="data")


__all__ = ["BundleArchive", "COMPRESSION_NONE", "COMPRESSION_ZSTD"]
