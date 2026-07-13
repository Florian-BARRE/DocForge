---
name: table-and-late-chunking
description: Tables are ALREADY markdown-serialized at chunk projection; late-chunking token spans must be computed server-side (BGE-M3 tokenizer != chunker tiktoken)
metadata:
  type: project
---

Two findings from the 2026-07-13 late-chunking + table-serialization research (features not yet built).

**Tables are already serialized — do NOT propose an enrich table node.**
TABLE blocks are rendered to markdown pipe tables at chunk projection, not at enrich.
Path: `chunk/base/passages.py` `PassageProjector.__block_text` (BlockType.TABLE branch) →
`ChunkerHelpers.render_table` → `__markdown_grid` (pipe-escape, header separator, ragged-row pad).
Gated by `BaseChunkerConfig.include_tables`/`tables_atomic` (both default True). Enrich only touches
figures because table structure is captured in `TableData` at parse — nothing to enrich.
- **Why:** the recurring "raw cell grid embeds poorly" ask is already solved in the chunk projection.
- **How to apply:** for any table-embedding request, improve `render_table`/`__markdown_grid`, never
  add a redundant enrich/table node. Only a TABLE with `table is None`/empty `cells` contributes nothing.

**Late chunking: chunk→full-doc token spans are derivable but must be computed server-side.**
One ingest run = one document, so all chunks in `EmbedConsumes` belong to one doc; the full-doc token
stream = concatenation of enabled (body) chunk `.text` in ordinal order (body chunks are ordinal-contiguous
at the front, furniture appended last). Chunk carries NO char/token offset — only `token_count`/`block_ids`/
`ordinal`; Block has `reading_order` but no char offset. Spans are re-derivable by re-tokenizing, BUT the
chunker counts with tiktoken `cl100k_base` while BGE-M3 tokenizes with XLM-RoBERTa — the counts differ, so
exact boundaries can only be computed where BGE-M3's tokenizer lives (bge_server). Overlap chunks duplicate
tokens; harmless for per-chunk mean-pooling.
- **Why:** determines that late chunking is a new `embed` kind delegating boundary+pool to bge_server, not
  a node-local computation, and that NO offset field needs adding to the Chunk artefact.
- **How to apply:** pipeline-side contract = send ordered enabled-chunk texts for one doc to a new server
  route; server owns tokenize/window(8192)/mean-pool and returns one dense vector per chunk. See
  [[chunker-role-routing]] for why furniture is excluded from the embedded set.
