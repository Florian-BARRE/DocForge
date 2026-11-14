# ====== Code Summary ======
# Characterization of the four sidecar parser nodes — dots_ocr, mineru, paddleocr_vl, pp_structure (safety
# net for extracting a shared SidecarParserNode / SidecarIRMapper). Each node is run through its public
# ``run`` over a canned sidecar response (httpx faked: no network) and the golden records (1) the request
# it sent (route, body, headers, params) and (2) what it returned: the quality score and the WHOLE
# DocumentIR as ``model_dump_json()`` — block order, types, heading levels and parent ids, normalised
# bboxes, table cells, reading order. The IR goldens are stored pretty-printed with the model's own key
# order; the test compares the exact text, so a refactor must reproduce a byte-identical IR. A drifted
# golden is a refactoring decision to review, never a test to fix: regenerate on purpose with
# CHARACTERIZATION_REGENERATE=1 (see support/golden_file.py).

# ====== Standard Library Imports ======
import asyncio
import json
import os
import pathlib

# ====== Third-Party Library Imports ======
import pytest

# ====== Internal Project Imports ======
from shared_libs.pipelines.ingest.nodes.parse.parser.base import BaseParserNode
from shared_libs.public_models import IntakeResult

# ====== Local Project Imports ======
from .support.fake_sidecar import FakeSidecar
from .support.golden_file import REGENERATE_ENV
from .support.sidecar_cases import CASES, SidecarCase

GOLDEN_DIR = pathlib.Path(__file__).resolve().parent / "goldens" / "sidecar_parsers"
PDF_BYTES = b"%PDF-1.7 characterization"
SOURCE_HASH = "characterization-hash"


def _run_parser(case: SidecarCase, monkeypatch: pytest.MonkeyPatch) -> tuple[FakeSidecar, object]:
    """Run the case's node over its canned response; return the fake sidecar and the node output."""
    sidecar = FakeSidecar(case.response)
    sidecar.install(monkeypatch)
    node = case.node_class(
        id="parse",
        config=case.config_class(base_url="http://sidecar.invalid:80", api_key="token"),
    )
    source = IntakeResult(source_hash=SOURCE_HASH, source_format="pdf", pdf_content=PDF_BYTES)
    output = asyncio.run(node.run(BaseParserNode.Consumes(source=source)))
    return sidecar, output


def _pretty(text: str) -> str:
    """Pretty-print a JSON text keeping the key order (so the golden diff stays readable)."""
    return json.dumps(json.loads(text), indent=1, ensure_ascii=False) + "\n"


def _assert_golden(name: str, actual: str) -> None:
    path = GOLDEN_DIR / name
    if os.environ.get(REGENERATE_ENV) == "1":
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(actual)
        return
    assert actual == path.read_text(), (
        f"{name} drifted from its golden. This is a characterization golden of today's output: a "
        f"change is a refactoring decision to review, not a test to fix (regenerate with {REGENERATE_ENV}=1)."
    )


@pytest.mark.parametrize("case_name", list(CASES))
def test_parser_ir_is_byte_identical_to_its_golden(
    case_name: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, output = _run_parser(CASES[case_name], monkeypatch)
    _assert_golden(f"{case_name}.ir.json", _pretty(output.ir.model_dump_json()))


@pytest.mark.parametrize("case_name", list(CASES))
def test_parser_request_and_score_match_their_golden(
    case_name: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    sidecar, output = _run_parser(CASES[case_name], monkeypatch)
    summary = {
        "request": sidecar.request,
        "score": output.score,
        "n_blocks": len(output.ir.blocks),
        "block_types": [block.block_type.value for block in output.ir.blocks],
    }
    _assert_golden(
        f"{case_name}.request.json", json.dumps(summary, indent=1, sort_keys=True) + "\n"
    )


@pytest.mark.parametrize("case_name", list(CASES))
def test_parser_without_a_pdf_view_degrades_to_an_empty_scored_zero_ir(
    case_name: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """No PDF view and no native format: no sidecar call, an empty IR keyed by the source hash, score 0."""
    case = CASES[case_name]
    sidecar = FakeSidecar(case.response)
    sidecar.install(monkeypatch)
    node = case.node_class(
        id="parse", config=case.config_class(base_url="http://sidecar.invalid:80")
    )
    source = IntakeResult(source_hash=SOURCE_HASH, source_format="docx", source_content=b"raw")
    output = asyncio.run(node.run(BaseParserNode.Consumes(source=source)))
    assert sidecar.request == {}
    assert output.score == 0.0
    assert json.loads(output.ir.model_dump_json())["blocks"] == []
    assert output.ir.doc_id == SOURCE_HASH
