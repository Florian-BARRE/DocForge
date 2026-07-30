# Contributing to DocForge

Thanks for your interest! This is a monorepo of four standalone [uv](https://docs.astral.sh/uv/)
projects, each with its own `pyproject.toml` / `uv.lock` and its own quality gate:

| Package | What it is | Gate |
|---|---|---|
| `src/docforge-rework` | The platform — FastAPI API + React frontend + arq worker + the graph engine | ruff format · ruff · pytest |
| `src/docforge_sdk` | The published typed client (`docforge-sdk` on PyPI) | ruff format · ruff · mypy --strict · pytest |
| `src/mcp` | The MCP server (thin `docforge-sdk` client) | ruff format · ruff · mypy · pytest |
| `src/bge_server` | Local BGE-M3 embed/rerank host | ruff format · ruff · mypy · pytest |

## Prerequisites

- [uv](https://docs.astral.sh/uv/getting-started/installation/) (Python 3.12).
- Docker + docker compose (only needed to run the live stack, not for unit tests).

## Working on a package

Each package is self-contained — `cd` into it and use uv:

```bash
cd src/docforge_sdk          # (or docforge-rework / mcp / bge_server)
uv sync --frozen             # install locked deps
uv run ruff format .         # auto-format
uv run ruff check .          # lint
uv run mypy .                # type-check (sdk uses: mypy --strict docforge_sdk)
uv run pytest -q             # unit tests (docforge-rework: pytest tests/units)
```

Unit suites are **fully mocked / serviceless** — no database, Qdrant or S3 needed. (The `docforge-rework`
suite reads app config, so CI materializes a placeholder `.env` from the template; locally you already
have one.) The SDK's live tests are opt-in: `uv run pytest -m live` needs a running API.

## The CI gate

Every push and PR runs the reusable gate in [`.github/workflows/gate.yml`](.github/workflows/gate.yml):
**format → lint → type-check → unit tests** for every package, plus the **frontend build** and an
**SDK↔backend OpenAPI coherence check**. A change can't merge unless the whole gate is green — and the
**same gate must pass before the SDK publishes** ([`release-sdk.yml`](.github/workflows/release-sdk.yml)).

Run the essentials locally before opening a PR:

```bash
# from each package you touched:
uv run ruff format --check . && uv run ruff check . && uv run pytest -q
```

## Keeping the SDK in sync with the API (important)

The `docforge-sdk` models are hand-written and mirror the backend's OpenAPI schema. If you change a
backend router model in `src/docforge-rework/app/backend/routers/**/models.py`, you **must** keep the SDK
coherent or CI's `sdk-parity` job goes red:

1. Regenerate the snapshot:
   ```bash
   cd src/docforge-rework
   uv run python app/scripts/dump_openapi.py > ../docforge_sdk/tests/openapi_snapshot.json
   ```
2. Update the matching model(s) in `src/docforge_sdk/docforge_sdk/models/` and, if the change adds an
   endpoint, its resource method (async **and** sync — a parity test enforces both) and the MCP tool.
3. `cd src/docforge_sdk && uv run pytest -q -m "not live"` (and `-m live` against a running stack if you can).

## Commit & PR conventions

- **Conventional-commit-style** messages: `feat(sdk): …`, `fix(mcp): …`, `docs: …`, `ci: …`, `refactor: …`.
- Keep PRs focused; make sure the gate is green.
- English for code, comments, docstrings and commit messages.
- Style: Google-style docstrings, type hints everywhere, small cohesive functions — see the code around
  what you're editing and match it.

## Releasing the SDK

The SDK publishes to PyPI via **Trusted Publishing** on a version tag:

```bash
# bump src/docforge_sdk/docforge_sdk/_version.py, commit, then:
git tag sdk-v0.2.0 && git push origin sdk-v0.2.0
```

The tag runs the full gate first; only if green does `publish` build the wheel/sdist and upload via OIDC
(a guard step fails the run if the tag version ≠ `_version.py`). Maintainers configure the PyPI trusted
publisher once (owner/repo/workflow `release-sdk.yml`/environment `pypi`).

## Reporting issues

Open an issue with steps to reproduce, the DocForge version, and relevant logs. Security-sensitive
reports: please disclose privately rather than in a public issue.
