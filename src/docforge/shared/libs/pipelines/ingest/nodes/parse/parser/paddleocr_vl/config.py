# ====== Code Summary ======
# Config of the PaddleOCR-VL 1.6 parser node — a NETWORK client, so its config is the per-collection
# endpoint (base_url + optional bearer + timeout) plus the sub-pipeline toggles it forwards to the
# sidecar on every request. There is NO device knob: PaddlePaddle CPU/GPU is a deployment concern
# owned by the sidecar image (invariant #7). Lean default: every heavy sub-pipeline OFF
# (chart/seal/image-block-OCR). The timeout defaults HIGH — PaddleOCR-VL is a VLM (~minutes per page
# on CPU), far slower than PP-StructureV3, so the base 300 s would truncate a real multi-page parse.

# ====== Third-Party Library Imports ======
from pydantic import Field, field_validator

# ====== Internal Project Imports ======
from shared_libs.pipelines.base import TimeoutRetryConfig


class ParserPaddleOcrVlConfig(TimeoutRetryConfig):
    """PaddleOCR-VL 1.6 sidecar endpoint + the sub-pipeline toggles forwarded per request.

    Timeout/retry come from ``TimeoutRetryConfig`` (``timeout_seconds`` overridden to 600 s — a VLM
    parse is slow, esp. multi-page on CPU); retry runs through the shared ``NetworkRetry`` loop in the
    node.
    """

    base_url: str = Field(
        default="http://paddle_server:80",
        description="PaddleOCR-VL sidecar endpoint. Defaults to the in-stack paddle_server so a parse "
        "chain escalation step added to a collection is reachable out of the box; override per "
        "collection to point at a remote sidecar.",
    )
    api_key: str = Field(default="", description="Bearer token when the sidecar requires one.")
    timeout_seconds: float = Field(
        default=600.0,
        gt=0,
        description="Per-request timeout (s). PaddleOCR-VL is a VLM — minutes per page on CPU, so "
        "the default is high; raise it further for long dense documents.",
    )
    use_chart_recognition: bool = Field(
        default=False,
        description="Run chart recognition (charts parsed into structured data). OFF by default — an "
        "extra heavy model; enable per deployment on chart-heavy corpora.",
    )
    use_seal_recognition: bool = Field(
        default=False,
        description="Run seal recognition. OFF by default — seals are not mapped into the IR.",
    )
    use_ocr_for_image_block: bool = Field(
        default=False,
        description="OCR the text inside image blocks inline. OFF by default — DocForge crops figures "
        "in the figure_render stage and OCRs them separately, so inline OCR here is redundant work.",
    )

    @field_validator("base_url", mode="before")
    @classmethod
    def _strip_whitespace(cls, value: object) -> object:
        """Strip pasted whitespace — a trailing newline breaks the HTTP request line."""
        return value.strip() if isinstance(value, str) else value


__all__ = ["ParserPaddleOcrVlConfig"]
