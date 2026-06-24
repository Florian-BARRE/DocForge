# Legacy & native-PDF baker

Pure-Python libraries (`python-docx`, `openpyxl`, `python-pptx`) can only write the **modern**
OOXML formats. DocForge also accepts the **legacy binary** formats (`.doc` / `.xls` / `.ppt`) and
the **native PDF** path, so this folder bakes those from the boosted modern sources using
**LibreOffice in a throwaway Docker container**, writing the results into `../../documents/<ext>/`
(committed). Each conversion's source is resolved by the catalog spec's `source_key`, so the legacy
documents inherit the rich content + complex layout of their boosted source.

| output | format | baked from (`source_key`) |
|---|---|---|
| `documents/doc/contrat_legacy.doc` | Word 97 | `contract_fr_docx` (FR contract, complex layout) |
| `documents/xls/tableau_legacy.xls` | Excel 97 | `data_fr_xlsx` (FR dashboard, 4 sheets / 48 rows) |
| `documents/ppt/presentation_legacy.ppt` | PowerPoint 97 | `report_fr_pptx` (FR report deck) |
| `documents/pdf/contrat_natif.pdf` | PDF | `contract_fr_docx` (FR contract) |

## Regenerate (needs Docker; only after a builder change)

```bash
cd src/docforge
uv run python -m tests.corpus.generation.legacy.bake_legacy          # bake what is missing
uv run python -m tests.corpus.generation.legacy.bake_legacy --force  # rebuild all
```

The first run builds a small cached image `docforge-libreoffice:bake` (from `Dockerfile.libreoffice`)
and converts inside a `--rm` container. Commit the updated binaries afterward. If absent, the corpus
loader simply skips them with a warning and the legacy/PDF live tests are skipped.
