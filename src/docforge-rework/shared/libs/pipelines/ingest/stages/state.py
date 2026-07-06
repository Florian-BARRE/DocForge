# ====== Code Summary ======
# PipelineState — the internal, canonical model of an ingestion pipeline that sits BETWEEN the blob
# and the stage view. Every stage-level operation is "read blob → PipelineState → mutate → assemble
# blob", and the view is derived straight from a PipelineState: keeping the toggles, provider kinds,
# per-node configs, enrich chains and contextualize stack in one small model is what lets the
# compiler ALWAYS emit a coherent, correctly wired blob (the assembler owns the wiring once). This
# module also holds the DEFAULT state — the stock pipeline every new collection opens on — from
# which default_blob() is assembled, so the skeleton has exactly one definition.

# ====== Third-Party Library Imports ======
from pydantic import BaseModel, ConfigDict, Field

# ====== Local Project Imports ======
from .models import ChainStep, StackMethod


class ChainSpec(BaseModel):
    """A fallback chain's canonical state — its family and its ordered steps."""

    model_config = ConfigDict(extra="forbid")

    family: str = Field(description="The model family the chain draws from (ocr / vlm / llm).")
    steps: list[ChainStep] = Field(
        default_factory=list, description="The ordered providers of the chain."
    )


class PipelineState(BaseModel):
    """
    The canonical state of an ingestion pipeline — enough to assemble its blob and derive its view.

    Attributes:
        intake_configs (dict): Config per fixed intake node id (convert base_url, admission policy…).
        parser_kind (str): The selected parser kind.
        parser_config (dict): The parser node's config.
        render_on (bool): Whether the figure-render stage is enabled.
        render_config (dict): The figure-render node's config.
        enrich_on (bool): Whether the per-figure enrichment stage is enabled.
        classify_config (dict): The figure-classifier node's config.
        chains (dict[str, ChainSpec]): The enrich chains, keyed by slot.
        chunker_kind (str): The selected chunking method kind.
        chunker_config (dict): The chunker node's config.
        stack (list[StackMethod]): The ordered contextualize methods (empty = stage off).
        metachunk_on (bool): Whether chunk-scope metadata generation is enabled.
        metachunk_config (dict): The chunk-metagen node's config.
        metadoc_on (bool): Whether document-scope metadata generation is enabled.
        metadoc_config (dict): The document-metagen node's config.
        embed_on (bool): Whether the embed stage is enabled.
        embed_kind (str): The selected embedder kind.
        embed_config (dict): The embedder node's config.
    """

    model_config = ConfigDict(extra="forbid")

    intake_configs: dict[str, dict] = Field(default_factory=dict)
    parser_kind: str = "docling"
    parser_config: dict = Field(default_factory=dict)
    render_on: bool = True
    render_config: dict = Field(default_factory=dict)
    enrich_on: bool = True
    classify_config: dict = Field(default_factory=dict)
    chains: dict[str, ChainSpec] = Field(default_factory=dict)
    chunker_kind: str = "structure_aware"
    chunker_config: dict = Field(default_factory=dict)
    stack: list[StackMethod] = Field(default_factory=list)
    metachunk_on: bool = True
    metachunk_config: dict = Field(default_factory=dict)
    metadoc_on: bool = True
    metadoc_config: dict = Field(default_factory=dict)
    embed_on: bool = True
    embed_kind: str = "bge_server"
    embed_config: dict = Field(default_factory=dict)


# The default endpoints of the stock pipeline — compose-internal services, overridden per collection
# in the studio. Kept here (not scattered) so the default topology has one description.
_VLM_ENDPOINT = {"base_url": "http://vlm:8000/v1", "model": "qwen2.5-vl"}


def default_state() -> PipelineState:
    """
    Build the stock pipeline state — the topology a new collection's editor opens on.

    Every built stage on, the recommended providers selected, the zero-cost contextualize stack
    (doc_meta → breadcrumb), and the enrich chains reviewed in the studio (a cheap-then-robust OCR
    chain for scanned text, a single VLM per visual class).

    Returns:
        PipelineState: The default canonical state (assembled into default_blob()).
    """
    return PipelineState(
        intake_configs={"convert": {"base_url": "http://gotenberg:3000"}},
        classify_config=dict(_VLM_ENDPOINT),
        chains={
            "scanned_text_ocr": ChainSpec(
                family="ocr",
                steps=[
                    ChainStep(kind="rapidocr", config={}, score_below=0.4),
                    ChainStep(kind="mistral", config={"api_key": "SET_ME"}),
                ],
            ),
            "photo_vlm": ChainSpec(
                family="vlm",
                steps=[ChainStep(kind="openai_compatible", config={
                    **_VLM_ENDPOINT, "system_prompt": "Caption this photo for retrieval."})],
            ),
            "chart_vlm": ChainSpec(
                family="vlm",
                steps=[ChainStep(kind="openai_compatible", config={
                    **_VLM_ENDPOINT,
                    "system_prompt": "Read this chart and transcribe its data for retrieval.",
                    "extract_table": True})],
            ),
            "diagram_vlm": ChainSpec(
                family="vlm",
                steps=[ChainStep(kind="openai_compatible", config={
                    **_VLM_ENDPOINT, "system_prompt": "Rewrite this diagram as searchable text."})],
            ),
        },
        stack=[
            StackMethod(kind="doc_meta", config={}),
            StackMethod(kind="breadcrumb", config={}),
        ],
        metachunk_config={"base_url": "http://llm:8000/v1", "model": "llm-default"},
        metadoc_config={"base_url": "http://llm:8000/v1", "model": "llm-default"},
        embed_config={"base_url": "http://bge_server:8008"},
    )


__all__ = ["ChainSpec", "PipelineState", "default_state"]
