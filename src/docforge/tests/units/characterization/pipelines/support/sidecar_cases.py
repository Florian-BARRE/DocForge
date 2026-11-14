# ====== Code Summary ======
# The canned sidecar responses the parser characterization feeds each parser node. The dots.ocr, MinerU
# and PaddleOCR-VL "contract" files are the fixtures of tests/units/nodes/fixtures (read in place, one
# copy); the small PaddleOCR-VL / PP-Structure responses are copied here from tests/units/nodes/
# test_parser_paddleocr_vl.py and test_parser_pp_structure.py (inline there, so not importable).
# Each case also names the node and config classes of its engine and the sidecar route it POSTs to.

# ====== Standard Library Imports ======
import json
import pathlib
from dataclasses import dataclass
from typing import Any

# ====== Internal Project Imports ======
from shared_libs.pipelines.base import NodeConfig
from shared_libs.pipelines.ingest.nodes.parse.parser.dots_ocr.config import ParserDotsOcrConfig
from shared_libs.pipelines.ingest.nodes.parse.parser.dots_ocr.core import ParserDotsOcrNode
from shared_libs.pipelines.ingest.nodes.parse.parser.mineru.config import ParserMineruConfig
from shared_libs.pipelines.ingest.nodes.parse.parser.mineru.core import ParserMineruNode
from shared_libs.pipelines.ingest.nodes.parse.parser.paddleocr_vl.config import (
    ParserPaddleOcrVlConfig,
)
from shared_libs.pipelines.ingest.nodes.parse.parser.paddleocr_vl.core import ParserPaddleOcrVlNode
from shared_libs.pipelines.ingest.nodes.parse.parser.pp_structure.config import (
    ParserPpStructureConfig,
)
from shared_libs.pipelines.ingest.nodes.parse.parser.pp_structure.core import ParserPpStructureNode

_NODE_FIXTURES = pathlib.Path(__file__).resolve().parents[3] / "nodes" / "fixtures"


def _contract(name: str) -> dict[str, Any]:
    return json.loads((_NODE_FIXTURES / name).read_text())


# Copied from test_parser_pp_structure.py (out-of-order reading order, a heading tree).
PP_STRUCTURE_SIMPLE_RESPONSE = {
    "n_pages": 1,
    "engine": {"paddleocr": "3.0.0"},
    "pages": [
        {
            "page_index": 0,
            "image_width": 1000,
            "image_height": 2000,
            "blocks": [
                # Deliberately out of reading order — the mapper must sort by reading_order.
                {
                    "label": "text",
                    "bbox": [100, 300, 900, 400],
                    "text": "Revenue grew 12% year over year and the outlook is positive.",
                    "reading_order": 2,
                },
                {
                    "label": "doc_title",
                    "bbox": [100, 50, 900, 150],
                    "text": "Quarterly Report",
                    "reading_order": 0,
                },
                {
                    "label": "paragraph_title",
                    "bbox": [100, 200, 500, 260],
                    "text": "Revenue",
                    "reading_order": 1,
                },
            ],
        }
    ],
}

# Copied from test_parser_pp_structure.py (a table, a formula, a figure, an unmapped seal).
PP_STRUCTURE_RICH_RESPONSE = {
    "n_pages": 1,
    "pages": [
        {
            "page_index": 0,
            "image_width": 100,
            "image_height": 100,
            "blocks": [
                {
                    "label": "table",
                    "bbox": [0, 0, 100, 20],
                    "html": "<table><tr><th>A</th><th>B</th></tr>"
                    "<tr><td>1</td><td>2</td></tr></table>",
                    "reading_order": 0,
                },
                {
                    "label": "formula",
                    "bbox": [0, 20, 100, 40],
                    "latex": "E=mc^2",
                    "reading_order": 1,
                },
                {"label": "image", "bbox": [50, 50, 100, 100], "reading_order": 2},
                # Unmapped label → skipped, never lands in the IR.
                {"label": "seal", "bbox": [0, 0, 10, 10], "reading_order": 3},
            ],
        }
    ],
}

# Copied from test_parser_paddleocr_vl.py (a table, a formula, a figure, an unmapped seal).
PADDLEOCR_VL_RICH_RESPONSE = {
    "n_pages": 1,
    "engine": {"paddleocr": "3.7.0", "pipeline": "PaddleOCR-VL-v1.6"},
    "pages": [
        {
            "page_index": 0,
            "image_width": 100,
            "image_height": 100,
            "blocks": [
                {
                    "label": "table",
                    "bbox": [0, 0, 100, 20],
                    "html": "<table><tr><th>A</th><th>B</th></tr>"
                    "<tr><td>1</td><td>2</td></tr></table>",
                    "reading_order": 0,
                },
                {
                    "label": "formula",
                    "bbox": [0, 20, 100, 40],
                    "latex": "E=mc^2",
                    "reading_order": 1,
                },
                {"label": "image", "bbox": [50, 50, 100, 100], "text": "", "reading_order": 2},
                # Unmapped label → skipped, never lands in the IR.
                {"label": "seal", "bbox": [0, 0, 10, 10], "reading_order": 3},
            ],
        }
    ],
}


@dataclass(frozen=True)
class SidecarCase:
    """One canned sidecar answer fed to one parser node."""

    engine: str
    node_class: type
    config_class: type[NodeConfig]
    response: dict[str, Any]


def _cases() -> dict[str, SidecarCase]:
    return {
        "dots_ocr.contract": SidecarCase(
            "dots_ocr", ParserDotsOcrNode, ParserDotsOcrConfig, _contract("dots_ocr_contract.json")
        ),
        "mineru.contract": SidecarCase(
            "mineru", ParserMineruNode, ParserMineruConfig, _contract("mineru_contract.json")
        ),
        "paddleocr_vl.captured_contract": SidecarCase(
            "paddleocr_vl",
            ParserPaddleOcrVlNode,
            ParserPaddleOcrVlConfig,
            _contract("paddleocr_vl_contract.json"),
        ),
        "paddleocr_vl.rich": SidecarCase(
            "paddleocr_vl",
            ParserPaddleOcrVlNode,
            ParserPaddleOcrVlConfig,
            PADDLEOCR_VL_RICH_RESPONSE,
        ),
        "pp_structure.simple": SidecarCase(
            "pp_structure",
            ParserPpStructureNode,
            ParserPpStructureConfig,
            PP_STRUCTURE_SIMPLE_RESPONSE,
        ),
        "pp_structure.rich": SidecarCase(
            "pp_structure",
            ParserPpStructureNode,
            ParserPpStructureConfig,
            PP_STRUCTURE_RICH_RESPONSE,
        ),
    }


CASES: dict[str, SidecarCase] = _cases()
