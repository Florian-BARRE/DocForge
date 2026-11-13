---
name: dependency-round
description: Handles docforge's weekly Dependabot round (the minor/patch PRs per lock file, the majors, the docker and compose bumps). Use when Dependabot PRs are open, when a dependency update, relock or `uv lock` is asked, or before touching a held package (docling, rapidocr, transformers, torch, postgres, redis, seaweedfs, a Python image).
---

# The weekly dependency round

Dependabot (`.github/dependabot.yml`) opens, each week, one grouped minor+patch PR per ecosystem and directory
(`actions-minor-patch`, `docforge-minor-patch`, `mcp-minor-patch`, ...), and each major alone. The rule from florian:
**break nothing, docling least of all.** A minor or patch is landed without asking; a major waits for florian.

## 1. Triage

`gh pr list --author "app/dependabot" --state open`, then sort every PR:

| What the PR is | What you do |
|---|---|
| minor/patch, GitHub Actions, npm, a `uv` project, a Docker or compose pin outside the holds below | land it (steps 2 to 5) |
| minor/patch that touches a package of the holds table | do not land that package; land the rest through a targeted relock (step 3) |
| the docling family (`docling`, `docling-slim`, `docling-core`, `docling-parse`, `docling-ibm-models`) | never in the round: its own request, florian merges it (step 6) |
| a major (any ecosystem) | do not merge, do not fix: one list for florian (step 7) |
| a PR a hold already covers (python image, postgres, redis, seaweedfs) | close it with a line saying which hold |

## 2. Twin PR, one per lock file

Dependabot's PR is not merged as is: its lock moves packages we hold, and CI on a bot branch is not ours to amend. Open a
**twin** from `main`: branch + worktree through the kit, one request per lock file or ecosystem
(`src/docforge`, `src/docforge_sdk`, `src/mcp`, `src/bge_server`, `src/paddle_server`, `src/mineru_server`,
`src/dots_ocr_server`, the frontend's `package-lock.json`, the workflows, the compose files). Title
`chore(deps): <what moves>`; the body says `Supersedes #N` (one line per original). Files stay to that lock file and its
`pyproject.toml`: a request that mixes two projects is two requests.

## 3. Relock, never by hand

Run `uv lock` from the project's directory (`cd src/docforge`); never edit a `uv.lock`. Pick the method by what must move:

- **Only some packages should land** (the usual case: hold the docling family):
  `uv lock --upgrade-package pydantic --upgrade-package langchain-core` moves exactly those packages and what they
  need, everything else stays. Check that `git diff -- uv.lock` shows only the intended version lines.
- **Put a package back at main's version** after a broader relock:
  `uv lock -P docling==X -P docling-slim==X -P docling-core==Y -P docling-parse==Z` (versions read from `main`'s
  `uv.lock`); it reverts only those and moves nothing else.
- **The whole project, minor/patch only** (`uv lock --upgrade` would take majors): copy `src/` to a scratch dir, add to
  each scratch `pyproject.toml` `[tool.uv] constraint-dependencies` one cap per locked package (`<major+1`; `<0.minor+1`
  for a 0.x; none for calver), `uv lock --upgrade` there, copy the scratch `uv.lock` back and run `uv lock` (no
  `--upgrade`) so the versions stay as preferences and the temporary caps leave the manifest. Diff the versions to
  confirm no major moved.

`bge_server` and `paddle_server`: `uv sync --extra cpu`, then `uv run --no-sync` (AGENTS.md, Pitfalls), or uv resolves
the multi-GB CUDA torch/paddle.

## 4. Verify

- `uv lock --check` in each project you relocked; `git diff` shows the versions you meant and no other.
- `aidk rules run done` (the project's checks: lock, deps, format, lint, tests, per project).
- When `src/docforge`'s own dependencies move (the core: FastAPI, pydantic, the parsers...), a smoke ingest on a real
  document, not only the unit tests; a compose or Dockerfile pin moving: `make config-check-all` (Docker, not in the
  checks; needs the gitignored `services/**/.env` copied from their `.env.example` temporarily, delete only those copies).
- Frontend: `npm ci` and the build in `src/docforge/app/frontend`.

## 5. Close the originals

Once the twin is merged (`aidk requests merge`, never by hand), close each superseded Dependabot PR with a comment
pointing to the twin, and delete its branch:

```bash
gh pr close N --delete-branch --comment "Superseded by #M (landed)."
```

Delete only the branches of the PRs you closed, after the twin is merged (Dependabot would reopen it otherwise).

## 6. Docling

Never inside a round. A docling bump is its own request with a before/after conversion check of the reference PDFs; florian
approves the version and merges it himself (open the request as a draft: `aidk work done --draft`, otherwise the queue
would merge it alone). Say in the request what changes in the conversion output and whether a reparse is needed.

## 7. Majors

A major, or a minimum-floor raise with breaking potential, waits for florian. Close the superseded Dependabot majors, then
send **one grouped list** (frontend, telemetry, backend, actions) with a recommendation each
(`aidk communication inbox ask`). florian's go makes each major its own small request, with proofs: docling family
versions unchanged, a reference PDF converted identically, an ingest smoke, the synthetic retrieval gate unchanged.
When in doubt, touch nothing and tell florian.

## Standing holds

| Hold | Where | Why | Lift when |
|---|---|---|---|
| docling family (`docling`, `-slim`, `-core`, `-parse`, `-ibm-models`) | `src/docforge`, `exclude-patterns` of its Dependabot group | florian: break nothing, docling least of all; every bump needs a before/after conversion check | never inside a round; its own request |
| `rapidocr` on 3.9.x | `src/docforge/uv.lock` only (a transitive of docling: no pin in `pyproject.toml`, no `ignore`: a relock that is not targeted would move it) | 3.10 needs `opencv-python-headless` while `rapidocr-onnxruntime` pulls `opencv-python`: both write the same `cv2` package | one opencv distribution is left |
| `transformers` `>=5` (and `huggingface-hub` `>=1` in `bge_server`) | `src/docforge`, `src/bge_server`, `ignore` in `dependabot.yml` | 5.x breaks docling's `AutoProcessor`, and `FlagReranker` (`prepare_for_model`) | docling, then FlagEmbedding, support 5 |
| `transformers` in `dots_ocr_server` held below 4.57 | `src/dots_ocr_server/pyproject.toml`, `dependabot.yml` | dots pins `transformers==4.56.1`: 4.57 made `video_processor` required and dots.ocr's remote processor omits it, which breaks the gpu extra | dots.ocr ships a compatible processor |
| `configplusplus` `>=0.4` | `src/paddle_server`, `ignore` in `dependabot.yml` | 0.4 needs `pyyaml>=6.0.3`, `paddlex` 3.7.2 pins `pyyaml==6.0.2`: unresolvable | `paddlex` relaxes its pin |
| `torch` `>=2.14`, `torchvision` `>=0.29` | `constraint-dependencies` of `src/docforge`, `src/bge_server`; `ignore` in `dependabot.yml` | cu126 is the last CUDA index with sm_70 kernels for the prod V100 and stops at torch 2.13; Dependabot does not read uv constraints, so the bump is unresolvable and turns the whole run red | the prod GPU moves off Volta (lift the cap and the ignore together) |
| Python 3.15 base images | every `Dockerfile` (`app`, `worker`, `mcp`, `bge_server`, `paddle_server`, ...), `ignore` of the `python` image in `dependabot.yml` | each builds the venv in a `uv:python3.12` stage and copies it into the runtime image: bumping only the runtime `FROM` breaks the venv at runtime while CI (build only) stays green | a Python upgrade moves the build and runtime stages of all images together, with torch/paddle wheels available |
| `postgres` 16.x, `redis` 7.4.x, `seaweedfs` 4.38 | `compose/compose.base.yml`, `/compose` entry of `dependabot.yml` | prod runs these versions on shared services florian does not upgrade; the dev images mirror them, so a major (postgres 18...) would test against something prod does not run | prod changes (florian) |

A hold that no longer matches the code (a lifted cap, a merged upstream fix) is corrected here and in `dependabot.yml`
in the same request.

Sources: m_09ac9249728e, m_1e2a7099cdbe, m_8df8ceb1df54, m_c08f499e6daf, m_352040d045bf, m_ee71e7d08357, m_79568e5b1856, m_0b55a1c6ad18, m_a36644925157, m_69bf07ee3d5f, m_1b226b099f5e, m_b1ea1d978d77, m_978b2d040d21, m_ae05e217991b
