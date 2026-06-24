# Unit + mocked tests (no Docker)

Everything that runs **without launching the stack** — the fast non-regression net.

- **`*.py` (root)** — pure unit tests of isolated logic: chunking, fusion (RRF/MMR), fingerprints,
  IR schema, admission, observability, config merge/explain, search post-processing, etc. No I/O.
- **`api/`** — mocked HTTP API tests: the FastAPI app is mounted **in-process** (httpx ASGI) and
  every `CONTEXT` service is replaced by a `MagicMock`. Each test drives a route and asserts its
  **status code + response shape** with no real DB / S3 / Redis / Qdrant. This is where every
  endpoint's full set of error codes (400/404/409/413/415/422/429/503…) is covered.

## Run

```bash
cd src/docforge && uv run pytest tests/units -q
```
