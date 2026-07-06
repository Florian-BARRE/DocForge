---
name: contextualize-llm-perchunk-traps
description: Per-chunk-LLM node review traps (contextualize llm_context; the shape metagen will copy) — O(n²) doc-view rebuild, unconditional whitespace flattening, over-broad keep_raw try, ChatOpenAI factory debt
metadata:
  type: project
---

The contextualize stage's `llm_context` node (`shared/libs/pipelines/ingest/nodes/contextualize/llm_context/core.py`) is the reference shape for any per-chunk-LLM node (metagen will almost certainly mirror it: build a document view from the chunks + bounded-concurrency gather + keep_raw/fail policy). Four traps to check on it AND on every copy:

1. **O(n²) document-view rebuild** — `__document_view` is called once PER CHUNK. For `DocumentScope.FULL` it rebuilds `"\n\n".join(all chunk texts).split()` every call (identical result n times); SECTION rebuilds per same-section sibling. Fix = precompute the scope-invariant view once per run (memoize by members signature) before the gather. On a 500-chunk doc this is hundreds of MB of GC churn.
2. **Unconditional whitespace flattening** — `" ".join(words[:cap])` collapses ALL newlines/paragraph structure even when UNDER the word cap. Only flatten when actually truncating: `if len(words) <= cap: return joined`.
3. **Over-broad keep_raw try** — the `try` in `_context_for` wraps `__document_view` too, so a real view-build bug degrades silently as a per-chunk "kept raw" warning. Build the view BEFORE the try; guard only the model call (`_situate`).
4. **ChatOpenAI 4th+ ad-hoc copy** — identical `ChatOpenAI(base_url, api_key or "unused", model, temperature, max_tokens, timeout)` is hand-rolled in llm_context, enrich/figure_classify, nodes/vlm/openai_compatible (+ OpenAIEmbeddings in chunk/chunker/semantic); canonical builder is nodes/llm/openai_compatible `_chat_model`. The `api_key or "unused"` magic literal is copy-pasted 4×. Recommend a leaf static factory `shared_libs/pipelines/clients/openai.py` (OpenAIClientFactory, python.md static-only) importable by both generic `nodes/*` and `ingest/nodes/*` without a cross-family import — kills client dup + the "unused" literal.

**Why:** flagged during the 2026-07-03 contextualize adversarial audit; all four verified by code-read (flagship `test_contextualize_stage.py` stays green — none break the contract). Non-blocking for the stage but F1+F2 should land before metagen copies the pattern at scale.
**How to apply:** when reviewing metagen or any new per-chunk / per-item LLM node, check these four before "done". Related engine-record blowup from byte artefacts: [[enrich-trace-and-failure-traps]]. Missing-strict-zip style nit also appears in contextualize base run() count.
