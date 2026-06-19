# ====== Code Summary ======
# StageDescriptorHelpers — builds the big per-stage descriptor list returned by
# DescribeSurface.describe_stages().  Each descriptor is a deeply nested dict literal
# (params + provider groups); extracting it here keeps describe.py focused on the
# auto-registry plumbing.  The provider lists are supplied by an injected auto_providers
# callable so this helper never touches registry state directly.

# ====== Standard Library Imports ======
from __future__ import annotations

from collections.abc import Callable
from typing import Any


class StageDescriptorHelpers:
    """
    Static builder for the pipeline stage descriptor list.

    ``build`` takes the ``auto_providers`` callable (``(category, kind) -> list[dict]``)
    from the host registry and returns the full ``{"stages": [...]}`` descriptor consumed
    by the playground UI.
    """

    def __new__(cls, *args: object, **kwargs: object) -> None:  # type: ignore[misc]
        """Block instantiation — this is a static-only helper class."""
        raise TypeError("StageDescriptorHelpers is a static-only class and cannot be instantiated.")

    @staticmethod
    def build(auto_providers: Callable[[str, str], list[dict]]) -> dict[str, Any]:
        """
        Build the full stage descriptor list for the playground UI.

        Args:
            auto_providers (Callable[[str, str], list[dict]]): Registry helper that returns
                the provider descriptors for a given (category, kind).

        Returns:
            dict: {"stages": [StageSchema, ...]} — each stage lists its groups and providers.
        """
        return {
            "stages": [
                {
                    "id": "s0", "label": "S0 · INGEST", "name": "INGEST",
                    "description": "blake3 fingerprint + SHA-256 dedup + S3 upload.",
                    "params": [], "groups": [],
                },
                {
                    "id": "s1", "label": "S1 · PARSE", "name": "PARSE",
                    "description": "Convert + parse the document into the canonical IR block tree.",
                    "params": [
                        {"name": "parse.gate.min_score", "label": "Parse gate — min_score", "type": "float",
                         "default": 0.5, "description": "Escalate when the parser's quality score is below this."},
                    ],
                    "groups": [
                        {"key": "parse.chain", "kind": "multi", "capability": "parse",
                         "label": "Parser chain (escalation order)",
                         "providers": auto_providers("parser", "multi")},
                    ],
                },
                {
                    "id": "s2", "label": "S2 · ENRICH", "name": "ENRICH",
                    "description": "Classify figures, then route to OCR / VLM / chart-to-data.",
                    "params": [
                        {"name": "enrich.chart_to_data", "label": "Chart → data", "type": "bool",
                         "default": False, "description": "Extract chart series into a structured table"},
                        {"name": "enrich.max_budget_usd", "label": "Max budget (USD)", "type": "float",
                         "default": 0.0, "description": "Per-job spend cap; 0 = no limit"},
                        {"name": "enrich.classifier_gate.min_score", "label": "Classifier gate — min_score",
                         "type": "float", "default": 0.5,
                         "description": "Escalate the classifier chain below this confidence."},
                        {"name": "enrich.ocr_gate.min_score", "label": "OCR gate — min_score",
                         "type": "float", "default": 0.85,
                         "description": "Escalate the OCR chain below this confidence."},
                        {"name": "enrich.vlm_gate.min_score", "label": "VLM gate — min_score",
                         "type": "float", "default": 0.5,
                         "description": "Escalate the VLM chain below this quality score."},
                    ],
                    "groups": [
                        {"key": "enrich.classifier_chain", "kind": "multi", "capability": "classifier",
                         "label": "Figure classifier chain (escalation order)",
                         "providers": auto_providers("classifier", "multi")},
                        {"key": "enrich.ocr_chain", "kind": "multi", "capability": "ocr",
                         "label": "OCR chain (escalation order)",
                         "providers": auto_providers("ocr", "multi")},
                        {"key": "enrich.vlm_chain", "kind": "multi", "capability": "vlm",
                         "label": "VLM chain (escalation order; empty = disabled)",
                         "providers": auto_providers("vlm", "multi")},
                    ],
                },
                {
                    "id": "s4", "label": "S4 · CHUNK", "name": "CHUNK",
                    "description": "Structure-aware chunking: heading skeleton + configurable intra-section split.",
                    "params": [
                        {"name": "chunk.reinject_breadcrumb", "label": "Reinject breadcrumb", "type": "bool",
                         "default": True, "description": "Prepend section path to embed_text"},
                        {"name": "chunk.merge_short_sections", "label": "Merge short sections", "type": "bool",
                         "default": True, "description": "Fold heading-only / tiny sections into neighbours"},
                        {"name": "chunk.hierarchical", "label": "Hierarchical chunks", "type": "bool",
                         "default": False, "description": "Emit a parent chunk per section over its children"},
                        {"name": "chunk.cross_references", "label": "Cross-references", "type": "bool",
                         "default": True, "description": "Detect see Figure/Article links between chunks"},
                    ],
                    "groups": [
                        {"key": "chunk.split_method", "kind": "single", "capability": "split_method",
                         "label": "Intra-section split method",
                         "providers": auto_providers("split_method", "single")},
                    ],
                },
                {
                    "id": "s5", "label": "S5 · CONTEXTUALIZE", "name": "CONTEXTUALIZE",
                    "description": (
                        "Build each chunk's embed_text header (doc title + heading "
                        "breadcrumb) before S6 embedding."
                    ),
                    "params": [
                        {"name": "contextualize.include_doc_title", "type": "bool", "default": True,
                         "label": "Include document title",
                         "description": "Prepend DocumentIR.title to the header unless it is already the first breadcrumb."},
                        {"name": "contextualize.include_breadcrumb", "type": "bool", "default": True,
                         "label": "Include heading breadcrumb",
                         "description": "Include the H1 > H2 > H3 trail in the header."},
                        {"name": "contextualize.breadcrumb_separator", "type": "str", "default": " > ",
                         "label": "Breadcrumb separator",
                         "description": "Joins title + breadcrumb segments (e.g. ' > ', ' / ', '\\n')."},
                        {"name": "contextualize.header_body_separator", "type": "str", "default": "\n\n",
                         "label": "Header / body separator",
                         "description": "Joins the header line to the chunk body (default = blank line)."},
                    ],
                    "groups": [],
                },
                {
                    "id": "s6", "label": "S6 · EMBED", "name": "EMBED",
                    "description": "Embed chunks and upsert multi-vector points into Qdrant.",
                    "params": [
                        {"name": "embed.gate.min_score", "label": "Embed gate — min_score", "type": "float",
                         "default": 0.5,
                         "description": "Escalate the embedding chain if a provider falls below this score."},
                    ],
                    "groups": [
                        {"key": "embed.chain", "kind": "multi", "capability": "embed",
                         "label": "Embedding chain (escalation order)",
                         "providers": auto_providers("embed", "multi")},
                    ],
                },
            ]
        }


# ------------------- Public API ------------------- #
__all__ = ["StageDescriptorHelpers"]
