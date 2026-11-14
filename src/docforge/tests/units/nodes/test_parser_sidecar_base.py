"""The shared sidecar parser base — what the four sidecar parsers (dots_ocr, mineru, paddleocr_vl,
pp_structure) inherit: the abstract-node contract, the mapper skeleton driven by a subclass vocabulary,
the bbox normalisation, and the registered kinds staying put. Offline: canned responses only."""

import pytest

from shared_libs.pipelines.ingest.nodes.parse.parser.dots_ocr.core import ParserDotsOcrNode
from shared_libs.pipelines.ingest.nodes.parse.parser.mineru.core import ParserMineruNode
from shared_libs.pipelines.ingest.nodes.parse.parser.paddleocr_vl.core import (
    ParserPaddleOcrVlNode,
)
from shared_libs.pipelines.ingest.nodes.parse.parser.pp_structure.core import (
    ParserPpStructureNode,
)
from shared_libs.pipelines.ingest.nodes.parse.parser.sidecar_base import (
    SidecarGeometry,
    SidecarIRMapper,
    SidecarParserNode,
)
from shared_libs.pipelines.registry import NodeRegistry
from shared_libs.public_models import BlockType

_NODES = {
    "dots_ocr": (ParserDotsOcrNode, "/parse", False),
    "mineru": (ParserMineruNode, "/parse", False),
    "paddleocr_vl": (ParserPaddleOcrVlNode, "/vl-parse", True),
    "pp_structure": (ParserPpStructureNode, "/layout-parsing", True),
}


@pytest.mark.parametrize("kind", list(_NODES))
def test_each_engine_subclasses_the_base_and_keeps_its_registered_kind(kind: str) -> None:
    node_class, endpoint, has_params = _NODES[kind]
    assert issubclass(node_class, SidecarParserNode)
    assert NodeRegistry.get("parser", kind) is node_class
    assert node_class.KIND == kind
    assert node_class.ENDPOINT == endpoint
    assert issubclass(node_class.MAPPER, SidecarIRMapper)
    node = node_class(id="p", config=node_class.Config())
    assert (node._query_params() is not None) is has_params


def test_the_base_itself_is_abstract_and_unregistered() -> None:
    assert "sidecar_base" not in NodeRegistry.kinds("parser")
    with pytest.raises(TypeError):
        SidecarParserNode(id="p", config=SidecarParserNode.Config(base_url="http://x"))


class _TinyMapper(SidecarIRMapper):
    LABEL_MAP = {"head": BlockType.HEADING, "body": BlockType.PARAGRAPH}
    HEADING_LEVELS = {"head": 3}
    LOG_LABEL = "tiny"


def test_mapper_skeleton_uses_the_subclass_vocabulary() -> None:
    response = {
        "pages": [
            {
                "page_index": 0,
                "image_width": 100,
                "image_height": 200,
                "blocks": [
                    {"label": "Body", "bbox": [0, 0, 50, 100], "reading_order": 2, "text": "b"},
                    {"label": "head", "bbox": [0, 0, 100, 200], "reading_order": 1, "text": "h"},
                    {"label": "unmapped", "bbox": [0, 0, 1, 1], "reading_order": 0, "text": "x"},
                ],
            }
        ],
        "n_pages": 1,
    }
    ir = _TinyMapper.map_response(response, doc_id="d", source_hash="h")
    assert [(b.block_type, b.level, b.reading_order) for b in ir.blocks] == [
        (BlockType.HEADING, 3, 0),
        (BlockType.PARAGRAPH, None, 1),
    ]
    assert ir.blocks[1].parent_id == ir.blocks[0].id
    assert ir.blocks[1].provenance.bbox == (0.0, 0.0, 0.5, 0.5)
    with pytest.raises(TypeError):
        _TinyMapper()


def test_geometry_normalises_orders_clamps_and_degrades() -> None:
    assert SidecarGeometry.normalize_bbox([50, 100, 0, 0], 100, 200) == (0.0, 0.0, 0.5, 0.5)
    assert SidecarGeometry.normalize_bbox([-10, 0, 500, 200], 100, 200) == (0.0, 0.0, 1.0, 1.0)
    assert SidecarGeometry.normalize_bbox([10, 10, 20, 20], 0, 0) == (1.0, 1.0, 1.0, 1.0)
    assert SidecarGeometry.normalize_bbox("bad", 100, 200) == (0.0, 0.0, 1.0, 1.0)
