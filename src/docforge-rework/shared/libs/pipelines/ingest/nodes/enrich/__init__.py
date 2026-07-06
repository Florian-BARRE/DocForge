# ---------------------- Stage 3 — ENRICH ---------------------- #
# Per-figure enrichment: extraction, classification (5 classes), the per-class OCR/VLM branches
# (generic families), and the fold back into the IR. Importing this stage imports every node folder.
from shared_libs.pipelines.registry import FamilyMode, NodeRegistry

NodeRegistry.register_family(
    "enrich",
    title="Enrichment",
    description=(
        "Per-figure enrichment logic: extract the figures, classify them (the switch driver), close branches with entries, fold everything back into the IR. The per-class work itself is done by the ocr/vlm chain families inside a foreach."
    ),
    mode=FamilyMode.STAGE,
)
NodeRegistry.auto_import(__name__)
