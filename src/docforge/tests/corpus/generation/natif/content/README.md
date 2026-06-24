# Multilingual content packs

Real **fr / en / es** prose, separated from layout, so builders compose long documents in any
language. Two archetypes per language: **contract** (legal: articles, clauses, definitions,
reversibility…) and **report** (narrative: KPIs, regional performance, risks…).

- `models.py` — `ContentPack` dataclass (title, abstract, section titles, a deep **paragraph pool**,
  contract clauses, lists, a wide table, footnote notes) + cycling helpers (`para`, `section_title`,
  `clause`) so a small pool composes a multi-page document.
- `fr.py` / `en.py` / `es.py` — `CONTRACT_<LANG>` + `REPORT_<LANG>` packs (real, language-correct
  text → drives the pipeline's language detection to the right code).
- `__init__.py` — `get_content(doc_type, language)` resolver.

The prose is intentionally substantial: builders cycle the pool into ~12 sections/articles to reach
real length and stress the chunker. The `searchable_phrase` of each pack is mirrored in
`../../catalog.py` so search tests can target each document.
