# Conversion non-regression corpus

A live smoke that ingests five small reference documents through the real stack and compares a
stable **fingerprint** of what the pipeline produced with a committed snapshot. Run it after a
dependency bump (docling, pypdf, pypdfium2, Gotenberg, Pillow, the chunker) or a pipeline change:
any silent change in the conversion fails with the exact leaves that moved.

| Document | Exercises |
|---|---|
| `pdf_native_contract` (`tests/units/nodes/fixtures/pdf/contrat_natif.pdf`) | native-text 12-page PDF: pypdf probe, docling, tables, figures (pypdfium2 render), structure chunking |
| `pdf_scanned_image_only` | image-only PDF: no text layer, 0 chunks + warning (the stock pipeline has no OCR provider) |
| `pdf_text_layer_metadata` | tiny text-layer PDF with document-info metadata |
| `docx_memo` (`fixtures/conversion_memo.docx`) | Office document: Gotenberg (LibreOffice) to PDF, heading + table |
| `png_text_image` (`fixtures/text_image.png`) | plain image: Gotenberg image to PDF, OCR of the rendered page |

## What is fingerprinted (per document)

- **document facts**: format, pages, language, title, source kind, status, chunk count, warning,
  source hash, pipeline version, whether the canonical PDF is the upload itself.
- **IR**: block / table / figure counts, and hashes of the structure, the text, the geometry (bbox,
  3 decimals), the tables and the figure crops. Block ids are replaced by reading-order ordinals.
- **chunks**: count, total tokens, and per chunk its tokens, characters, text hash, block ordinals,
  page, role, strategy, heading path; plus one **boundary hash** over all of it.
- **markdown view**: length and hash. **trace**: node kinds that ran.
- **API response shapes**: the type skeleton of `GET document`, `chunks`, `ir`, job status and a
  trace event, so a field or type change shows up.

Not captured: UUIDs, timestamps, durations, and the converted PDF's hash (Gotenberg output embeds
timestamps and is not byte-stable).

## Run

```bash
# a stack with the app, the worker and Gotenberg (the embed stage is disabled by default: conversion only)
cd src/docforge
DOCFORGE_LIVE_API_URL=http://127.0.0.1:<api port> uv run python -m pytest tests/live/test_conversion_corpus_live.py -m live
```

- `DOCFORGE_SMOKE_RECORD=1` records the snapshot (after an INTENDED change: review the `git diff` of
  `tests/live/snapshots/conversion_corpus.json`, it is the change report).
- `DOCFORGE_SMOKE_SNAPSHOT=/path/file.json` compares with / writes another file: record at one
  commit, run at another, to diff two refs.
- `DOCFORGE_SMOKE_WITH_EMBED=1` keeps the embed stage (needs the BGE host).
- The offline harness tests are `tests/units/live_corpus/`.

## Rebuilding the binary fixtures

`fixtures/build_fixtures.py` regenerates the `.docx` and `.png` (stdlib + Pillow). A changed fixture
changes the source hash: re-record the snapshot.

## Not covered yet (future extensions)

- Retrieval quality (hit@k): the `rag_eval` baseline is inert (#218); a search smoke belongs here
  once it is live, ingesting with the embed stage on.
- Documents needing an LLM/VLM/OCR provider (figure classification, contextualisation, scans with OCR).
- More types: xlsx, pptx, html/markdown/csv, non-Latin text, corrupted and password-protected files.
