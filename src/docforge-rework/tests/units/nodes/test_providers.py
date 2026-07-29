"""Per-item provider contracts: registry, lazy imports, describes, and a REAL local OCR read
through the node contract. Ported from the scratchpad's test_providers.py.
"""

import sys

import shared_libs.pipelines.nodes  # noqa: F401 — auto-discovery
from shared_libs.pipelines.nodes.ocr.base import OcrConsumes
from shared_libs.pipelines.nodes.ocr.rapidocr.core import OcrRapidOcrConfig, OcrRapidOcrNode
from shared_libs.pipelines.nodes.vlm.base import (
    BaseVlmConfig,
    BaseVlmHelpers,
    BaseVlmNode,
    VlmConsumes,
)
from shared_libs.pipelines.nodes.vlm.openai_compatible.core import VlmOpenAICompatibleNode
from shared_libs.pipelines.registry import NodeRegistry
from shared_libs.public_models import FigureItem


def test_ocr_and_vlm_kinds_are_registered_and_rapidocr_stays_lazy() -> None:
    # Superset checks (not equality): other node test modules in this session register their
    # own fake ocr/vlm kinds under the SAME real families (collection order is alphabetical, so
    # test_enrich_stage/test_enrich_failsoft's fakes may already be registered by the time this
    # runs) — see [[noderegistry-global-state]].
    assert {"rapidocr", "mistral"} <= set(NodeRegistry.kinds("ocr"))
    assert "openai_compatible" in NodeRegistry.kinds("vlm")
    # Not asserting rapidocr_onnxruntime is ABSENT here: other node tests in this session may
    # have already exercised it — the "stays lazy until use" guarantee is proven in the last
    # test below instead (module import alone never pulls it in for a fresh interpreter).


def test_vlm_describe_exposes_the_per_item_face_with_no_min_score() -> None:
    described = VlmOpenAICompatibleNode.describe()
    props = described.config_schema["properties"]
    for key in ("system_prompt", "extract_table", "base_url", "model", "max_tokens", "temperature"):
        assert key in props, key
    assert "min_score" not in props  # escalation lives on the graph now, not the config
    assert [(s.name, s.artefact_type) for s in described.consumes] == [("figure", "FigureItem")]
    # VLM is now scored (confidence threaded for ScoreBelow escalation) — score slot first, then entry.
    assert [(s.name, s.artefact_type) for s in described.produces] == [
        ("score", "float"),
        ("entry", "EnrichmentEntry"),
    ]


def test_rapidocr_describe_has_no_endpoint_knobs() -> None:
    described = OcrRapidOcrNode.describe()
    assert described.config_schema["properties"] == {}
    assert [(s.name, s.artefact_type) for s in described.produces] == [
        ("score", "float"),
        ("figure", "FigureItem"),
    ]


def test_extract_table_parses_the_fenced_block_and_strips_it() -> None:
    description, rows = BaseVlmHelpers.extract_table(
        "Revenue rises.\n\n```table\nQ | R\nQ1 | 10\n```"
    )
    assert rows == [["Q", "R"], ["Q1", "10"]]
    assert "```" not in description


class FakeVlm(BaseVlmNode):
    """A child overriding only ``_describe`` — proves the base class's flow (prompt composed,
    entry closed, kind/ocr carried from the item) without a real endpoint."""

    KIND = "test_providers_fake_vlm"
    NAME = "F"
    SUMMARY = "t"
    Config = BaseVlmConfig

    async def _describe(self, image: bytes, context: str, system_prompt: str) -> tuple[str, float]:
        assert "END your answer" in system_prompt  # table contract appended
        assert context == "ocr said: hello"
        return "A bar chart.\n```table\nA | B\n1 | 2\n```", 1.0


async def test_vlm_base_flow_composes_prompt_and_closes_the_entry() -> None:
    node = FakeVlm(id="v", config=BaseVlmConfig(system_prompt="Read this chart.", extract_table=True))
    figure = FigureItem(block_id="fig1", image=b"png", kind="chart", read_text="ocr said: hello")
    out = await node.run(VlmConsumes(figure=figure))
    assert out.entry.block_id == "fig1"
    assert out.entry.kind == "chart"
    assert out.entry.description == "A bar chart."
    assert out.entry.data_table == [["A", "B"], ["1", "2"]]
    assert out.entry.ocr_text == "ocr said: hello"


async def test_real_rapidocr_reads_a_rendered_image_through_the_node_contract() -> None:
    """A REAL onnxruntime OCR pass (the ``worker`` dependency group provides it in .venv)."""
    import io

    import pytest

    # Real-provider test: it needs the heavy `worker` group (pillow + rapidocr-onnxruntime).
    # When the suite runs on the dev group alone, skip rather than error on the missing modules.
    pytest.importorskip("PIL")
    pytest.importorskip("rapidocr_onnxruntime")

    from PIL import Image, ImageDraw

    image = Image.new("RGB", (420, 90), "white")
    ImageDraw.Draw(image).text((12, 30), "FACTURE 2024 TOTAL 1500 EUR", fill="black")
    buf = io.BytesIO()
    image.save(buf, format="PNG")

    ocr = OcrRapidOcrNode(id="o", config=OcrRapidOcrConfig())
    source = FigureItem(block_id="f1", image=buf.getvalue())
    result = await ocr.run(OcrConsumes(figure=source))
    assert result.score > 0.5
    assert "1500" in result.figure.read_text.replace(" ", "")
    assert source.read_text == ""  # the input item was NOT mutated (copy relay)
    assert "rapidocr_onnxruntime" in sys.modules  # loaded lazily, on use
