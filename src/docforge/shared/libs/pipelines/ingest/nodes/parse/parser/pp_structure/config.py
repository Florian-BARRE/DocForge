# ====== Code Summary ======
# Config of the PP-StructureV3 (PaddleOCR) parser node — a NETWORK client, so its config is the
# per-collection endpoint (base_url + optional bearer + timeout) plus the sub-pipeline toggles it
# forwards to the sidecar on every request. There is NO device knob: PaddlePaddle CPU/GPU is a
# deployment concern owned by the sidecar image (invariant #7). Lean default: table recognition ON,
# everything else OFF (formula/seal/orientation/unwarping) — the fastest cold start for born-digital
# PDFs, each toggle overridable per collection without a sidecar rebuild.

# ====== Third-Party Library Imports ======
from pydantic import Field, field_validator

# ====== Internal Project Imports ======
from shared_libs.pipelines.base import TimeoutRetryConfig


class ParserPpStructureConfig(TimeoutRetryConfig):
    """PP-StructureV3 sidecar endpoint + the sub-pipeline toggles forwarded per request.

    Timeout/retry come from ``TimeoutRetryConfig`` (``timeout_seconds`` overridden to 300 s — layout
    parsing is slow on CPU); retry runs through the shared ``NetworkRetry`` loop in the node.
    """

    base_url: str = Field(
        default="http://paddle_server:80",
        description="PP-StructureV3 sidecar endpoint. Defaults to the in-stack sidecar so a parse "
        "chain escalation step added to a collection is reachable out of the box; override per "
        "collection to point at a remote sidecar.",
    )
    api_key: str = Field(default="", description="Bearer token when the sidecar requires one.")
    timeout_seconds: float = Field(
        default=300.0,
        gt=0,
        description="Per-request timeout (s). Layout parsing is slow, esp. multi-page on CPU.",
    )
    use_table_recognition: bool = Field(
        default=True,
        description="Run the table-recognition sub-pipeline so tables come back as HTML the mapper "
        "flattens into a grid. ON by default — DocForge cares about tables.",
    )
    use_formula_recognition: bool = Field(
        default=False,
        description="Run formula recognition so formulas come back as LaTeX. OFF by default "
        "(extra model + latency); enable per deployment on formula-heavy corpora.",
    )
    use_seal_recognition: bool = Field(
        default=False,
        description="Run seal recognition. OFF by default — seals are not mapped into the IR.",
    )
    use_doc_orientation_classify: bool = Field(
        default=False,
        description="Classify and correct page orientation before layout. OFF by default — rarely "
        "needed on born-digital PDFs.",
    )
    use_doc_unwarping: bool = Field(
        default=False,
        description="Geometrically unwarp distorted (photographed) pages before layout. OFF by "
        "default — only helps camera captures, not born-digital PDFs.",
    )

    @field_validator("base_url", mode="before")
    @classmethod
    def _strip_whitespace(cls, value: object) -> object:
        """Strip pasted whitespace — a trailing newline breaks the HTTP request line."""
        return value.strip() if isinstance(value, str) else value


__all__ = ["ParserPpStructureConfig"]
