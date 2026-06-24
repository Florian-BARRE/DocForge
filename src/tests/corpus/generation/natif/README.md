# Native builders

One builder class per **modern** format, all subclassing `BaseDocumentBuilder`. Each composes a
deliberately **long and complex** document from a multilingual content pack so the pipeline is
pushed on chunking, layout parsing and language detection.

## Content + layout bricks

- `content/` — multilingual **content packs** (`fr` / `en` / `es`) for two archetypes,
  **contract** and **report**: real prose pools, contract clauses, lists, a wide table and
  footnote-style notes. `get_content(doc_type, language)` resolves the pack. Driving length from a
  pool (cycled) yields multi-page documents that stress the chunker.
- `docx_layout.py` — `DocxLayoutHelper`: the complex Word layout ops python-docx doesn't expose
  (multi-column sections, running headers/footers, **landscape** sections, **nested** tables,
  multi-level lists).
- `base.py` — `BaseDocumentBuilder` (ABC) + shared helpers.
- `image_factory.py` — `ImageFactory`: synthetic PNG figures (chart / diagram / photo / logo).

## Builders

- `docx_builder.py` — title + running header/footer, multi-column section, long body (contract
  articles or report sections), embedded figures, a **landscape** wide table with a **nested**
  table, footnote notes, multi-level lists. Driven by `spec.doc_type` + `spec.language`.
- `html_builder.py` — CSS multi-column section, colspan + nested tables, base64 data-URI figures,
  many prose sections, footnotes. Multilingual.
- `pptx_builder.py` — title + bulleted slides (cycled), image, native table, native chart. Multilingual.
- `xlsx_builder.py` — multi-sheet, styled headers, merged cells, formula, native chart, embedded image.
- `markdown_builder.py` — rich CommonMark (the 415 negative fixture; not ingestable).

A builder returns raw `bytes`; `../generator.py` writes them to `../../documents/<ext>/`.
