---
name: flagembedding-m3-internals
description: FlagEmbedding 1.4.0 BGEM3FlagModel internals — pooling method, colbert shape, shared forward pass, what encode() does/doesn't expose. Grounds late-chunking + colbert design.
metadata:
  type: project
---

Verified 2026-07-13 by downloading and reading the actual `flagembedding-1.4.0-py3-none-any.whl` source
(pinned version in `src/bge_server/pyproject.toml` — `FlagEmbedding>=1.2.10`, uv.lock resolves 1.4.0).
Not derivable by reading this repo alone — the facts live in the third-party dependency's source.

**Class chain**: `FlagEmbedding.BGEM3FlagModel` is `FlagEmbedding.inference.embedder.encoder_only.m3.M3Embedder`.
`M3Embedder.model` is `EncoderOnlyEmbedderM3ModelForInference` (subclass of `EncoderOnlyEmbedderM3Model`).
That class's `.model` attribute (`self.model = base_model['model']`) is the raw HF `AutoModel`
(XLM-RoBERTa). So from the service, the raw transformer is reachable at
`self.embed_model.model.model` and the tokenizer at `self.embed_model.tokenizer`.

**One shared forward pass feeds dense + sparse + colbert.** `EncoderOnlyEmbedderM3ModelForInference.forward()`
always computes `last_hidden_state = self.model(**text_input, return_dict=True).last_hidden_state` ONCE,
unconditionally, then conditionally derives whichever of dense/sparse/colbert heads were requested from
that single tensor. Passing `return_dense=True, return_sparse=True, return_colbert_vecs=True` together in
one `encode()` call costs exactly ONE transformer forward pass, not three.
**Consequence for this repo**: `libs/bge_models/service.py` `encode_dense()` (line ~236) and
`encode_sparse()` (line ~275) each call `.encode()` separately — two full forward passes today for what
could be one combined call. Latent perf optimization, not yet acted on (batching engine's two workers
are separate on purpose for independent queue formation, so combining would need engine redesign too).

**Dense pooling is CLS-token, NOT mean-pooling.** `M3Embedder.DEFAULT_POOLING_METHOD = "cls"`,
`_dense_embedding()` returns `last_hidden_state[:, 0]` (then L2-normalized). A `"mean"` pooling branch
exists in the code but BGE-M3's shipped checkpoint uses `"cls"`. This means any "late chunking" scheme
that mean-pools raw per-token hidden states over a chunk's token span produces a vector in a
**different representational path** than what `encode_dense()` normally returns for that same text —
they are not guaranteed to be directly comparable via cosine similarity to query vectors embedded the
normal way. This is a fundamental model-fit caveat (the original Jina "Late Chunking" paper worked
because Jina's embedder is mean-pooling-native; BGE-M3 is not), not an implementation detail — applies
regardless of whether pooling happens server-side or client-side.

**Colbert vectors**: `colbert_linear(last_hidden_state[:, 1:])`, masked, then L2-normalized (same
`F.normalize` call as dense). Dim = `colbert_dim` config (default `-1` → `hidden_size` = 1024, so same
1024 as dense by default). Post-processing (`M3Embedder.encode_single_device`'s `_process_colbert_vecs`)
slices to `attention_mask.sum() - 1` rows — drops the CLS row (already excluded upstream) and keeps every
other real token including EOS/SEP. Variable length per text = (real token count) - 1.

**No public API returns raw `last_hidden_state`.** `encode()` only ever crosses the `dense_vecs` /
`lexical_weights` / `colbert_vecs` boundary. Getting per-token pre-pooling vectors (needed for literal
late-chunking mean-pool) requires bypassing `encode()`/`encode_single_device()` and calling the raw HF
model forward directly via the `self.embed_model.model.model` attribute chain — an undocumented,
version-fragile internal path (not a stable FlagEmbedding contract; could break on a FlagEmbedding bump).

**Tokenizer is fast (Rust-backed)**: `BAAI/bge-m3` on HF ships `tokenizer.json` at repo root, so
`AutoTokenizer.from_pretrained` loads `XLMRobertaTokenizerFast`, which supports
`return_offsets_mapping=True` — char-offset-to-token-index mapping is available if a raw-hidden-state
path is ever built.

Full one-time research contract (late chunking + colbert endpoint design options) was delivered to the
orchestrator on 2026-07-13 for synthesis with the `pipeline`/`backend` agents — not re-derived here;
see conversation history / PIPELINE.md once a decision lands. If Feature 1 (late chunking) or Feature 2
(colbert endpoint) get implemented, update this memory with the actual chosen contract and endpoint shape.
