# Corpus

**20** hard, fully synthetic documents used by the live tier — **contract** & **report** archetypes
in **fr / en / es**, with complex layouts (multi-column sections, **landscape** pages, merged &
**nested** tables, multi-level lists), embedded figures/charts and lots of real prose — so ingestion
is pushed on **chunking**, layout parsing and **language detection** across every important format.
Content is data-driven by the multilingual packs in `generation/natif/content/`.

## Layout

```
corpus/
├── documents/<ext>/   COMMITTED files, one folder per extension (loaded at test time)
├── generation/
│   ├── natif/         pure-Python builders for modern formats (docx/xlsx/pptx/html/md)
│   ├── legacy/        LibreOffice baker for legacy binaries (doc/xls/ppt) + native pdf
│   └── generator.py   regenerates the modern committed documents
├── spec.py            DocumentSpec (what + expected minimums) + CorpusDocument
├── catalog.py         CATALOG — the single source of truth (one spec per document)
├── manifest.py        CorpusManifest — lookups (by key/format, ingestable, negatives)
└── loader.py          load_corpus() — resolves the catalog to documents/<ext>/
```

## Model

- **`catalog.py`** declares each document and its **minimum** recovered structure
  (figures/tables/pages/chunks), calibrated to real Docling output (margins below observed).
- **Generation is separate from loading**: `generation/` produces the files (run once + commit);
  `loader.load_corpus()` only reads them, so test runs are deterministic and fast.
- `md` is the **non-ingestable** negative fixture (drives the 415 test).

## Use in tests

```python
from tests.corpus import load_corpus
manifest = load_corpus()
doc = manifest.get("rich_docx")        # or manifest.by_format("docx")
bytes_ = doc.read_bytes()              # upload payload
```

Regeneration commands: see `generation/README.md` and `documents/README.md`.
