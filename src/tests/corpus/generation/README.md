# Corpus generation

Code that **produces** the committed documents in `../documents/<ext>/`. Not imported at test time
(tests only load via `corpus.loader`). Run it once, and again whenever a builder changes — then
commit the refreshed files.

- **`natif/`** — pure-Python builders for the modern formats, the multilingual **content packs**
  (`content/`: fr/en/es × contract+report), a `DocxLayoutHelper` for complex Word layout
  (columns/landscape/nested tables/multi-level lists) and `ImageFactory` (Pillow). No external tooling.
- **`legacy/`** — bakes the legacy binaries (`.doc`/`.xls`/`.ppt`) and the native `.pdf` from a
  generated source (resolved by each spec's `source_key`), inside a throwaway **LibreOffice** Docker
  container (pure-Python libs can't write those formats). See `legacy/README.md`.
- **`generator.py`** — `CorpusGenerator.regenerate()`: rebuilds every modern document into
  `../documents/<ext>/`.

```bash
cd src/docforge
uv run python -m tests.corpus.generation.generator          # modern -> documents/
uv run python -m tests.corpus.generation.legacy.bake_legacy # legacy + pdf -> documents/
```
