"""FigureRenderNode serialises PDFium process-wide (issue #242).

PDFium is not thread-safe: two ``figure_render`` runs overlapping in one worker process (two jobs on
the thread pool, an HTML job's Gotenberg preview PDF rasterised next to another job's) crashed the
process with SIGSEGV / SIGTRAP. Two tests lock the fix:

* a fast unit test over a STUBBED ``pypdfium2`` that asserts at most one PDFium call is in flight;
* an end-to-end regression with the REAL pypdfium2, run in a SUBPROCESS (a crash must fail the
  test, not kill pytest): N rounds of ``asyncio.gather(node.run(a), node.run(b))`` over a 12-page
  fixture PDF must exit 0 with outputs byte-identical to a serial run. It fails (crash) without
  the lock.

This module doubles as the subprocess probe: ``python test_figure_render_concurrency.py <pdf>``.
"""

import asyncio
import hashlib
import pathlib
import subprocess
import sys
import threading
import time
import types

import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]
FIXTURE_PDF = pathlib.Path(__file__).resolve().parent / "fixtures" / "pdf" / "contrat_natif.pdf"
ROUNDS = 3  # concurrent rounds per probe run (the unlocked code crashed on the first round, 3/3)


# ---------------------------------------------------------------------------------------------
# Probe — runs inside the subprocess (and nowhere else)
# ---------------------------------------------------------------------------------------------
def _probe_consumes(pdf: bytes):
    """A fresh (ingest, IR) pair with ONE figure block on page 0, so crops are exercised too."""
    from shared_libs.pipelines.ingest.nodes.parse.figure_render.core import FigureRenderConsumes
    from shared_libs.public_models import DocumentIR, IntakeResult
    from shared_libs.public_models.ir.block import Block
    from shared_libs.public_models.ir.enums import BlockType
    from shared_libs.public_models.ir.provenance import Provenance

    figure = Block(
        id="fig",
        block_type=BlockType.FIGURE,
        provenance=Provenance(page=0, bbox=(0.1, 0.1, 0.6, 0.5)),
        reading_order=0,
    )
    return FigureRenderConsumes(
        ingest=IntakeResult(source_hash="h", pdf_content=pdf, page_count=12),
        ir=DocumentIR(doc_id="d", source_hash="h", n_pages=12, blocks=[figure]),
    )


def _digest(out) -> str:
    """Hash every output byte of one run: page renders + the embedded figure crop."""
    sha = hashlib.sha256()
    for page in out.pages.pages:
        sha.update(page.image)
    sha.update(out.ir.figure_blocks[0].figure.crop)
    return sha.hexdigest()


async def _probe(pdf: bytes, rounds: int) -> None:
    from shared_libs.pipelines.ingest.nodes.parse.figure_render.core import (
        FigureRenderConfig,
        FigureRenderNode,
    )

    node = FigureRenderNode(id="r", config=FigureRenderConfig())
    reference = _digest(await node.run(_probe_consumes(pdf)))
    for round_number in range(rounds):
        outs = await asyncio.gather(node.run(_probe_consumes(pdf)), node.run(_probe_consumes(pdf)))
        for out in outs:
            if _digest(out) != reference:
                raise SystemExit(f"round {round_number}: concurrent output differs from serial")
    print("PROBE_OK")


def _probe_main(pdf_path: str, rounds: int) -> None:
    """Wire ``shared_libs`` exactly like tests/conftest.py does, then run the probe."""
    module = types.ModuleType("shared_libs")
    module.__path__ = [str(REPO_ROOT / "shared" / "libs")]
    sys.modules["shared_libs"] = module
    asyncio.run(_probe(pathlib.Path(pdf_path).read_bytes(), rounds))


# ---------------------------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------------------------
def test_concurrent_renders_do_not_crash_and_match_the_serial_run() -> None:
    """Real pypdfium2, two overlapping renders per round, in a subprocess: exit 0, same bytes."""
    pytest.importorskip("pypdfium2")  # worker dependency group; absent from the light unit env
    pytest.importorskip("PIL")
    result = subprocess.run(
        [sys.executable, str(pathlib.Path(__file__).resolve()), str(FIXTURE_PDF), str(ROUNDS)],
        capture_output=True,
        text=True,
        timeout=300,
    )
    assert result.returncode == 0, (
        f"probe exited {result.returncode} (139 = SIGSEGV, 133 = SIGTRAP): {result.stderr[-800:]}"
    )
    assert "PROBE_OK" in result.stdout


class _Image:
    """A stand-in PIL image: just enough surface for the node (size, save, crop)."""

    width = 10
    height = 10

    def save(self, buffer, format: str) -> None:
        buffer.write(b"png")

    def crop(self, _box) -> "_Image":
        return self


class _Probe:
    """Counts the PDFium calls in flight across threads."""

    def __init__(self) -> None:
        self.guard = threading.Lock()
        self.in_flight = 0
        self.peak = 0

    def enter(self) -> None:
        with self.guard:
            self.in_flight += 1
            self.peak = max(self.peak, self.in_flight)
        time.sleep(0.01)  # a window wide enough for another thread to overlap

    def leave(self) -> None:
        with self.guard:
            self.in_flight -= 1


def _stub_pypdfium2(probe: _Probe) -> types.ModuleType:
    """A fake ``pypdfium2`` whose every call registers with the probe."""

    class Bitmap:
        def to_pil(self) -> _Image:
            probe.enter()
            probe.leave()
            return _Image()

        def close(self) -> None:
            probe.enter()
            probe.leave()

    class Page:
        def render(self, scale: float) -> Bitmap:
            probe.enter()
            probe.leave()
            return Bitmap()

        def close(self) -> None:
            probe.enter()
            probe.leave()

    class PdfDocument:
        def __init__(self, _data: bytes) -> None:
            probe.enter()
            probe.leave()

        def __len__(self) -> int:
            probe.enter()
            probe.leave()
            return 4

        def __getitem__(self, _index: int) -> Page:
            probe.enter()
            probe.leave()
            return Page()

        def close(self) -> None:
            probe.enter()
            probe.leave()

    return types.SimpleNamespace(PdfDocument=PdfDocument)


async def test_pdfium_calls_never_overlap_across_concurrent_runs(monkeypatch) -> None:
    """Four overlapping node runs: at most ONE PDFium call is in flight at any instant."""
    from shared_libs.pipelines.ingest.nodes.parse.figure_render.core import (
        FigureRenderConfig,
        FigureRenderConsumes,
        FigureRenderNode,
    )
    from shared_libs.public_models import DocumentIR, IntakeResult

    probe = _Probe()
    monkeypatch.setitem(sys.modules, "pypdfium2", _stub_pypdfium2(probe))
    node = FigureRenderNode(id="r", config=FigureRenderConfig())
    consumes = FigureRenderConsumes(
        ingest=IntakeResult(source_hash="h", pdf_content=b"%PDF", page_count=4),
        ir=DocumentIR(doc_id="d", source_hash="h", n_pages=4, blocks=[]),
    )

    outs = await asyncio.gather(*(node.run(consumes) for _ in range(4)))

    assert all(len(out.pages.pages) == 4 for out in outs)  # the renders really happened
    assert probe.peak == 1  # serialised: never two PDFium calls at once


if __name__ == "__main__":
    _probe_main(sys.argv[1], int(sys.argv[2]))
