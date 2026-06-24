# DocForge test suite

Structured like the source tree: strict hierarchy, reusable bricks, a README at every level.

```
tests/
├── corpus/        synthetic test documents + the code that produces them
│   ├── documents/<ext>/   the committed files, one folder per extension
│   ├── generation/        builders (natif/) + legacy baker (legacy/) + generator
│   ├── spec.py catalog.py manifest.py loader.py   the corpus model + loader
│   └── README.md
├── libs/          reusable building blocks (LiveClient, …)
├── live_test/     end-to-end tests on the RUNNING stack (real documents)
└── units/         unit + mocked-API tests (no Docker)
    └── api/        mocked HTTP endpoints (in-process ASGI)
```

## Tiers

| Tier | Path | Needs the stack? | What it proves |
|---|---|---|---|
| **Units** | `units/` | No | Pure logic (chunking, fusion, IR, admission, observability, config…). |
| **Mocked API** | `units/api/` | No | Every route's orchestration + status codes, `CONTEXT` fully mocked. |
| **Live e2e** | `live_test/` | **Yes** | The real pipeline on the real corpus: Gotenberg → Docling → TEI → Qdrant via the real API. |

## Running

```bash
cd src/docforge

# Fast tiers — no Docker
uv run pytest tests/units -q

# Live tier — requires the dev stack up (auto-skips otherwise)
docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d
uv run pytest tests/live_test -v -s

# Everything
uv run pytest -q
```

## Corpus in one line

**20** hard synthetic documents — **contract** & **report** archetypes in **fr / en / es**, complex
layouts (columns, landscape, nested tables, multi-level lists) and lots of prose to stress chunking
+ language detection — across docx/xlsx/pptx/html and baked doc/xls/ppt/pdf, plus an `md` 415
negative. Produced once by `corpus/generation/` and **committed** under `corpus/documents/<ext>/`;
tests only **load** them. See `corpus/README.md`.
