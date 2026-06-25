---
name: provider-raise-on-failure
description: Providers must RAISE on engine failure (not return degraded result) so the Chain escalates
metadata:
  type: feedback
---

A provider's own try/except around its engine/inference must **re-raise** on a genuine failure —
never fabricate a degraded "success" result.

**Why:** `Chain.call()` only escalates to the next provider when `attempt.succeeded is False`
(i.e. the call raised). The `ChainGate` checks `not attempt.succeeded` first. If a provider catches
its crash and returns e.g. `OcrResult(text="", confidence=0.0)` or `ClassificationResult(PHOTO,0.5)`,
the chain sees a "successful" result, records `error=None`, and either accepts the degraded output
or escalates only via min_score — defeating escalation AND erasing the real error from the per-attempt
trace. This was the masked-failure class fixed in the 2026-06-25 robustness audit.

**How to apply:** in any provider's `_extract_sync` / `_infer_sync` / `embed` / etc., the terminal
`except` logs and `raise`s. A genuinely empty-but-successful result (OCR ran fine, found no text) is
fine to return — only mask-the-crash returns are the bug. The "all providers failed" terminal case is
handled by the CONSUMER: `Chain.call` returns `ChainOutcome(result=None)`, and:
  - S1 parse / S6 embed -> RAISE (pipeline cannot proceed without IR / vectors).
  - S2 OCR/VLM/classifier -> best-effort: routers return None; FigureEnricher applies the documented
    PHOTO fallback when classification is None (figure enrichment is opt-in, never fails the doc).

Fixed providers: `ocr/paddle`, `classifier/vit_onnx`, `classifier/layout_labels`.
`Chain.call` itself NEVER raises on exhaustion — each stage decides. Verify any new provider re-raises.

Related: [[document-status-state-machine]]
