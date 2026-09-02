"""DocumentSampler (edge, pure over rows): row→SampleStats aggregation. An EXACT page count (ingest
already ran) is trusted and counted as probed; a not-yet-ingested binary document derives pages from
byte size; a text-native format derives tokens straight from byte size. The provenance count that
drives the accuracy caveat is asserted too. No DB — the sampler folds plain row objects."""

import pathlib
import sys
from types import SimpleNamespace

# The ``backend`` package lives under app/ — put it on the path exactly as the api conftest's
# fastapi_app fixture does, so this pure test module imports it at collection time without booting.
_APP_DIR = str(pathlib.Path(__file__).resolve().parents[3] / "app")
if _APP_DIR not in sys.path:
    sys.path.insert(0, _APP_DIR)

from backend.libs.estimate import DocumentSampler  # noqa: E402
from shared_libs.pipelines.ingest.estimate import EstimateAssumptions  # noqa: E402


def _doc(fmt: str, file_size: int, page_count: int | None) -> SimpleNamespace:
    """A stand-in document row carrying only the fields the sampler reads."""
    return SimpleNamespace(format=fmt, file_size=file_size, page_count=page_count)


def _assumptions() -> EstimateAssumptions:
    """Round numbers so the arithmetic is checkable by hand."""
    return EstimateAssumptions(tokens_per_page=500.0, bytes_per_token=4.0, bytes_per_page=40000.0)


def test_exact_page_count_is_trusted_and_marked_probed() -> None:
    stats = DocumentSampler.aggregate([_doc("pdf", 1_000_000, 20)], _assumptions())
    assert stats.total_pages == 20.0
    assert stats.total_text_tokens == 20 * 500.0
    assert stats.pages_from_probe == 1


def test_binary_without_page_count_derives_pages_from_size() -> None:
    # 400_000 bytes / 40_000 bytes-per-page = 10 pages, size-derived (not probed).
    stats = DocumentSampler.aggregate([_doc("pdf", 400_000, None)], _assumptions())
    assert stats.total_pages == 10.0
    assert stats.pages_from_probe == 0


def test_text_native_derives_tokens_from_size() -> None:
    # 4_000 bytes / 4 bytes-per-token = 1000 tokens; pages are the derived view (1000/500 = 2).
    stats = DocumentSampler.aggregate([_doc("md", 4_000, None)], _assumptions())
    assert stats.total_text_tokens == 1000.0
    assert stats.total_pages == 2.0
    assert stats.pages_from_probe == 0


def test_mixed_batch_sums_and_counts_probed() -> None:
    docs = [_doc("pdf", 1_000_000, 20), _doc("pdf", 400_000, None), _doc("txt", 4_000, None)]
    stats = DocumentSampler.aggregate(docs, _assumptions())
    assert stats.sampled_documents == 3
    assert stats.document_count == 3
    assert stats.total_pages == 20.0 + 10.0 + 2.0
    assert stats.pages_from_probe == 1


def test_document_count_override_enables_scaling() -> None:
    stats = DocumentSampler.aggregate(
        [_doc("pdf", 1_000_000, 20)], _assumptions(), document_count=100
    )
    assert stats.sampled_documents == 1
    assert stats.document_count == 100
