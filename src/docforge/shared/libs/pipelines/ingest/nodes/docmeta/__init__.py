# ---------------------- Stage — DOCMETA (document-level metadata) ---------------------- #
# Doc-level derivations over the parsed IR that stand apart from figure enrichment: today the
# language detector (post-parse, pre-enrich). A dedicated family keeps the "one family per stage
# role" convention — enrich is figure/ForEach-shaped, so a doc-level IR → IR node lives here.
# Importing this stage imports every node folder; everything self-registers by existing here.
from shared_libs.pipelines.registry import FamilyMode, NodeRegistry

NodeRegistry.register_family(
    "docmeta",
    title="Document metadata",
    description=(
        "Document-level derivations over the parsed IR — today the language detector, which stamps "
        "the IR's ISO 639-1 language so downstream figure OCR and the catalog can use it."
    ),
    mode=FamilyMode.STAGE,
)
NodeRegistry.auto_import(__name__)
