---
name: page-indexing-zero-based
description: Document page numbers are 0-indexed end to end; tests/clients that use page 1 as "first page" are off-by-one
metadata:
  type: project
---

Page numbering across DocForge is **0-indexed**, not 1-indexed.

**Why:** `block.prov.page` originates from the parser and is consumed directly as a PyMuPDF
page index — `libs/pipeline/stages/s1_parse/renderer.py` does `doc[block.prov.page]` after a
`page_num >= doc.page_count` bounds check. The pages router (`backend/routers/collections/documents/pages/router.py`)
surfaces it unchanged: `PageInfo(page=b.page)`, and `_render_page_png(pdf, page_number)` also
treats its argument as a 0-based fitz index. So for an N-page document the valid page indices are
`0 .. N-1`. `GET .../pages/{n}` and `.../pages/{n}/screenshot` with `n=1` target the **second** page.

**How to apply:** When reviewing page/screenshot tests or any client (live_client, SDK, MCP):
- Treat `pages/0` as the guaranteed-present first page; `pages/N` (== total_pages) is the out-of-range edge.
- Flag tests that request `pages/1` calling it "the first page" — they only pass because they pin a
  ≥2-page doc (e.g. corpus `rich_docx`, min_pages=2) and would fail on a 1-page document.
- Note that `get_page` echoes `page=page_number` unconditionally, so an assertion like
  `body["page"] == 1` cannot catch the off-by-one — it always echoes whatever was requested.
- Prefer asserting against `pages/list` (`body["pages"][0]["page"]`) instead of hardcoding 1.

Related: [[search_pipeline_antipatterns]] (other stale-contract traps in this codebase).
