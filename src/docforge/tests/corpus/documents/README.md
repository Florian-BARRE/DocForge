# Corpus documents (committed)

The actual corpus files, **one folder per extension**. These are produced **once** by
`../generation/` and **committed** — at test time they are only **loaded** (deterministic, fast,
inspectable). Tests never generate documents on the fly.

| folder | format | how it is produced |
|---|---|---|
| `docx/` `xlsx/` `pptx/` `html/` `md/` | modern | `../generation/natif` (python-docx / openpyxl / python-pptx / hand-authored) |
| `doc/` `xls/` `ppt/` | legacy binary | `../generation/legacy` (LibreOffice container) |
| `pdf/` | native PDF | `../generation/legacy` (baked from the FR contract docx) |

**20 documents** total (the catalog matrix): **contract** & **report** archetypes in **fr / en / es**
(docx ×6, html ×3, pptx ×3), **3 multilingual xlsx** dashboards, the `md` negative, and **4 baked**
legacy/PDF. Each is deliberately **long and complex** — deep heading hierarchy, multi-column
sections, merged & **nested** tables, **landscape** pages, embedded figures/charts, multi-level
lists, accented unicode, real fr/en/es prose — so ingestion exercises **chunking**, layout parsing
and **language detection**. Expected minimums per document live in `../catalog.py`.

`md/note_synthese.md` is **not ingestable** (DocForge rejects `.md`); it drives the 415
unsupported-format negative test.

## Regenerate (only after changing a builder)

```bash
cd src/docforge
uv run python -m tests.corpus.generation.generator            # modern formats
uv run python -m tests.corpus.generation.legacy.bake_legacy   # legacy + pdf (needs Docker)
```
Then **commit** the updated files.
