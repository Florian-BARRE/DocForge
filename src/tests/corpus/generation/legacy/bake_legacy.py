# ====== Code Summary ======
# One-time baker for the committed legacy + native-PDF corpus documents. Pure-Python libraries
# cannot write the legacy binary Office formats (.doc/.xls/.ppt); this script builds the rich modern
# sources with the natif builders, then converts them to legacy binaries + a native PDF inside a
# throwaway LibreOffice container, writing the results into tests/corpus/documents/<fmt>/. Run ONCE
# (and after a builder change); the produced binaries are committed.
#
# Usage (from src/docforge):
#   uv run python -m tests.corpus.generation.legacy.bake_legacy          # bake what is missing
#   uv run python -m tests.corpus.generation.legacy.bake_legacy --force  # rebuild every fixture

# ====== Standard Library Imports ======
from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

# ─── Make the tests package importable when run as a standalone script ────────────
# legacy -> generation -> corpus -> tests -> docforge (the app root that holds `tests`).
_DOCFORGE_ROOT = Path(__file__).resolve().parents[4]
if str(_DOCFORGE_ROOT) not in sys.path:
    sys.path.insert(0, str(_DOCFORGE_ROOT))

# ====== Internal Project Imports ======
from tests.corpus.catalog import CATALOG, LEGACY_FORMATS
from tests.corpus.generation.natif import DocxCorpusBuilder, PptxCorpusBuilder, XlsxCorpusBuilder
from tests.corpus.loader import DOCUMENTS_DIR

# ─── Constants ────────────────────────────────────────────────────────────────────
LEGACY_DIR = Path(__file__).resolve().parent          # holds the Dockerfile
DOCKERFILE = LEGACY_DIR / "Dockerfile.libreoffice"
IMAGE_TAG = "docforge-libreoffice:bake"

# Builder per generated source format used to produce the conversion input.
_GEN_BUILDERS = {
    "docx": DocxCorpusBuilder,
    "xlsx": XlsxCorpusBuilder,
    "pptx": PptxCorpusBuilder,
}


def _docker_path(path: Path) -> str:
    """Return a Docker-Desktop-friendly absolute path (forward slashes, drive letter)."""
    return str(path.resolve()).replace("\\", "/")


def _spec_by_key(key: str):
    """Return the catalog spec with the given key (the generated source to convert FROM)."""
    for spec in CATALOG:
        if spec.key == key:
            return spec
    raise KeyError(f"No catalog spec with key {key!r}.")


def _out_path(spec) -> Path:
    """Return the committed destination for a legacy/PDF document: documents/<fmt>/<filename>."""
    return DOCUMENTS_DIR / spec.fmt / spec.filename


def _build_image() -> None:
    """Build (or reuse the cached) LibreOffice converter image."""
    print(f"[bake] building converter image {IMAGE_TAG} (cached after first run)...")
    subprocess.run(
        ["docker", "build", "-t", IMAGE_TAG, "-f", str(DOCKERFILE), str(LEGACY_DIR)],
        check=True,
    )


def _convert(workdir: Path, src_name: str, target_fmt: str) -> None:
    """Run a one-shot LibreOffice conversion of one file inside the converter container."""
    subprocess.run(
        [
            "docker", "run", "--rm",
            "-v", f"{_docker_path(workdir)}:/data",
            IMAGE_TAG,
            "soffice", "--headless", "--convert-to", target_fmt, "--outdir", "/data",
            f"/data/{src_name}",
        ],
        check=True,
    )


def _bake_one(spec, workdir: Path) -> None:
    """Build the modern source for one legacy spec, convert it, and commit the result."""
    # 1. Build the generated SOURCE this document is baked from (resolved by spec.source_key)
    src_spec = _spec_by_key(spec.source_key)
    stem = Path(spec.filename).stem
    src_name = f"{stem}.{src_spec.fmt}"
    data = _GEN_BUILDERS[src_spec.fmt](spec=src_spec).build()
    (workdir / src_name).write_bytes(data)

    # 2. Convert to the legacy/PDF target inside the container
    _convert(workdir, src_name, spec.fmt)

    # 3. Verify the conversion produced a non-empty file, then commit it under documents/<fmt>/
    produced = workdir / f"{stem}.{spec.fmt}"
    if not produced.is_file() or produced.stat().st_size == 0:
        raise RuntimeError(f"Conversion produced no output for {spec.filename!r}.")
    dest = _out_path(spec)
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(produced, dest)
    print(f"[bake] OK {spec.fmt}/{spec.filename} ({dest.stat().st_size} bytes)")


def main() -> int:
    """Bake all missing (or, with --force, all) legacy + PDF corpus documents."""
    # 1. Parse arguments
    parser = argparse.ArgumentParser(description="Bake committed legacy/PDF corpus documents.")
    parser.add_argument("--force", action="store_true", help="Rebuild even existing documents.")
    args = parser.parse_args()

    # 2. Determine what needs baking
    targets = [s for s in CATALOG if s.fmt in LEGACY_FORMATS]
    pending = [s for s in targets if args.force or not _out_path(s).is_file()]
    if not pending:
        print("[bake] nothing to do — all legacy/PDF documents present (use --force to rebuild).")
        return 0

    # 3. Build the converter image once, then bake each pending document in a temp workdir
    _build_image()
    with tempfile.TemporaryDirectory(prefix="docforge-bake-") as td:
        workdir = Path(td)
        for spec in pending:
            _bake_one(spec, workdir)

    print(f"[bake] done — {len(pending)} document(s) written under {DOCUMENTS_DIR}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
