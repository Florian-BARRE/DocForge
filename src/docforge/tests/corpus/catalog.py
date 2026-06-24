# ====== Code Summary ======
# The corpus catalog: the canonical list of DocumentSpecs (the matrix of type x language x format)
# and the format-routing sets the generator/baker use. Generated formats are built in-process by
# generation/natif; legacy + native PDF are baked from a generated source (spec.source_key) via
# generation/legacy. Pipeline-recovered minimums are conservative (Docling runs with table-structure
# detection OFF in the slim image and Gotenberg->Docling is lossy), so the suite asserts ">= an
# observed value", never an exact round-trip.

# ====== Standard Library Imports ======
from __future__ import annotations

# ====== Local Project Imports ======
from .spec import DocumentSpec

# Formats generated in-process by a builder (no external tooling required).
GENERATED_FORMATS: frozenset[str] = frozenset({"docx", "xlsx", "pptx", "html", "md"})

# Formats that need LibreOffice; baked once from a generated source and committed.
LEGACY_FORMATS: frozenset[str] = frozenset({"doc", "xls", "ppt", "pdf"})

# Distinctive search phrases, kept in sync with the content packs (generation/natif/content).
_PHRASE = {
    ("contract", "fr"): "résiliation pour manquement grave et réversibilité des données.",
    ("report", "fr"): "trajectoire de croissance soutenue malgré la pression sur les marges.",
    ("contract", "en"): "termination for material breach and reversibility of data.",
    ("report", "en"): "a sustained growth trajectory despite pressure on margins.",
    ("contract", "es"): "resolución por incumplimiento grave y reversibilidad de los datos.",
    ("report", "es"): "una trayectoria de crecimiento sostenido pese a la presión sobre los márgenes.",
}
_TITLE = {
    ("contract", "fr"): "Contrat-cadre de prestations de services managés",
    ("report", "fr"): "Rapport annuel d'activité et de performance numérique",
    ("contract", "en"): "Master Agreement for Managed Services",
    ("report", "en"): "Annual Activity and Digital Performance Report",
    ("contract", "es"): "Contrato marco de prestación de servicios gestionados",
    ("report", "es"): "Informe anual de actividad y desempeño digital",
}


def _docx(doc_type: str, lang: str, filename: str) -> DocumentSpec:
    """Build a docx spec for a (type, language) pair — long, complex layout."""
    return DocumentSpec(
        key=f"{doc_type}_{lang}_docx", fmt="docx", filename=filename,
        title=_TITLE[(doc_type, lang)], searchable_phrase=_PHRASE[(doc_type, lang)],
        doc_type=doc_type, language=lang, expected_language=lang,
        min_pages=4, min_figures=1, min_tables=1, min_headings=3, min_chunks=10,
        description=f"{doc_type} {lang}: colonnes, en-têtes/pieds, section paysage, table imbriquée, "
                    "listes multi-niveaux, longue prose (stress chunking + détection de langue).",
    )


def _html(lang: str, filename: str) -> DocumentSpec:
    """Build an html report spec for a language."""
    return DocumentSpec(
        key=f"report_{lang}_html", fmt="html", filename=filename,
        title=_TITLE[("report", lang)], searchable_phrase=_PHRASE[("report", lang)],
        doc_type="report", language=lang, expected_language=lang,
        min_pages=2, min_figures=1, min_tables=0, min_headings=3, min_chunks=8,
        description=f"rapport {lang} HTML : colonnes CSS, table colspan + imbriquée, figures data-URI, prose longue.",
    )


def _pptx(lang: str, filename: str) -> DocumentSpec:
    """Build a pptx report spec for a language."""
    return DocumentSpec(
        key=f"report_{lang}_pptx", fmt="pptx", filename=filename,
        title=_TITLE[("report", lang)], searchable_phrase=_PHRASE[("report", lang)],
        doc_type="report", language=lang, expected_language=lang,
        min_pages=5, min_figures=1, min_tables=0, min_chunks=5,
        description=f"présentation {lang} : titre, puces multi-niveaux, image, table native, graphique natif.",
    )


def _xlsx(lang: str, filename: str) -> DocumentSpec:
    """Build a multilingual data-dashboard xlsx spec (content drawn from the report pack)."""
    return DocumentSpec(
        key=f"data_{lang}_xlsx", fmt="xlsx", filename=filename,
        title=_TITLE[("report", lang)], searchable_phrase=_PHRASE[("report", lang)],
        doc_type="data", language=lang, expected_language=None,
        min_pages=2, min_figures=1, min_tables=0, min_chunks=5,
        description=f"tableur {lang} : ~48 lignes, titre fusionné, formats/bordures, panneaux figés, "
                    "formules inter-feuilles, 2 graphiques natifs, feuille de commentaire (prose), image.",
    )


# The full catalog (matrix). Keys are stable; tests reference documents by key.
CATALOG: tuple[DocumentSpec, ...] = (
    # ─── docx: contract x {fr,en,es} + report x {fr,en,es} ───────────────────────
    _docx("contract", "fr", "contrat_fr.docx"),
    _docx("contract", "en", "contract_en.docx"),
    _docx("contract", "es", "contrato_es.docx"),
    _docx("report", "fr", "rapport_fr.docx"),
    _docx("report", "en", "report_en.docx"),
    _docx("report", "es", "informe_es.docx"),
    # ─── html report x {fr,en,es} ────────────────────────────────────────────────
    _html("fr", "rapport_fr.html"),
    _html("en", "report_en.html"),
    _html("es", "informe_es.html"),
    # ─── pptx report x {fr,en,es} ────────────────────────────────────────────────
    _pptx("fr", "presentation_fr.pptx"),
    _pptx("en", "presentation_en.pptx"),
    _pptx("es", "presentacion_es.pptx"),
    # ─── xlsx data dashboards x {fr,en,es} (long + complex; commentary gives language signal) ──
    _xlsx("fr", "tableau_fr.xlsx"),
    _xlsx("en", "dashboard_en.xlsx"),
    _xlsx("es", "tablero_es.xlsx"),
    # ─── markdown — NOT ingestable (drives the 415 negative test) ─────────────────
    DocumentSpec(
        key="note_md", fmt="md", filename="note_synthese.md",
        title="Note de synthèse Markdown",
        searchable_phrase="format markdown non supporté à l'ingestion.",
        doc_type="note", language="fr", expected_language=None, ingestable=False,
        description="Markdown riche utilisé comme fixture de format non supporté (415).",
    ),
    # ─── committed legacy binaries (baked from a generated source) ────────────────
    DocumentSpec(
        key="legacy_doc", fmt="doc", filename="contrat_legacy.doc",
        title=_TITLE[("contract", "fr")], searchable_phrase=_PHRASE[("contract", "fr")],
        doc_type="contract", language="fr", expected_language="fr", source_key="contract_fr_docx",
        min_pages=4, min_chunks=10, description="Word 97 binaire, baké depuis le contrat FR riche.",
    ),
    DocumentSpec(
        key="legacy_xls", fmt="xls", filename="tableau_legacy.xls",
        title=_TITLE[("report", "fr")], searchable_phrase=_PHRASE[("report", "fr")],
        doc_type="data", language="fr", expected_language=None, source_key="data_fr_xlsx",
        min_pages=2, min_chunks=5, description="Excel 97 binaire, baké depuis le xlsx FR enrichi.",
    ),
    DocumentSpec(
        key="legacy_ppt", fmt="ppt", filename="presentation_legacy.ppt",
        title=_TITLE[("report", "fr")], searchable_phrase=_PHRASE[("report", "fr")],
        doc_type="report", language="fr", expected_language="fr", source_key="report_fr_pptx",
        min_pages=5, min_chunks=5, description="PowerPoint 97 binaire, baké depuis le pptx FR riche.",
    ),
    # ─── committed native PDF (bypasses Gotenberg → direct Docling path) ──────────
    DocumentSpec(
        key="native_pdf", fmt="pdf", filename="contrat_natif.pdf",
        title=_TITLE[("contract", "fr")], searchable_phrase=_PHRASE[("contract", "fr")],
        doc_type="contract", language="fr", expected_language="fr", source_key="contract_fr_docx",
        min_pages=4, min_figures=1, min_tables=0, min_chunks=10,
        description="PDF natif riche (baké depuis le contrat FR) — éprouve le chemin sans conversion.",
    ),
)
