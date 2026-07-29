# Driving the DocForge UI in a real browser (screenshots / e2e)

The VM has **no host browser** (missing `libnss3` & co, and `sudo` needs a password). Use the official
**Playwright Docker image** (browsers + system libs baked in) with `--network host` to reach the dev
frontend at `localhost:10046`. No sudo — the user is in the `docker` group.

## One-shot setup

```bash
# Match the image tag to the playwright npm version used by the script.
docker pull mcr.microsoft.com/playwright:v1.62.0-noble
# The script needs the `playwright` JS module resolvable (browsers come from the image):
cd src/docforge-rework/app/frontend/scripts && npm i playwright@1.62.0   # once, creates node_modules/
```

## Run

```bash
SP="$(pwd)/src/docforge-rework/app/frontend/scripts"   # holds ui-shot.mjs + node_modules
docker run --rm --network host \
  -e DOCFORGE_API_TOKEN='df_root_...'                  # the API root token (AUTH_ROOT_TOKEN) \
  -v "$SP":/work -w /work \
  mcr.microsoft.com/playwright:v1.62.0-noble \
  node ui-shot.mjs --out /work/shot.png --path "DemoCollection,Documents,doc.pdf,Pages"
# then Read src/docforge-rework/app/frontend/scripts/shot.png
```

## Gotchas (DocForge-specific)

- **Auth**: the frontend is a bearer client — the token lives in `localStorage["docforge_api_token"]`.
  The script seeds it with `addInitScript` BEFORE any page script, because `apiFetch` calls
  `clearApiToken()` on a 401, so a token injected *after* the first `/collections` call gets wiped.
- **No deep-link URLs**: routing is hand-rolled `useState<View>` (no router), so you can't navigate by
  URL — pass `--path` as the sequence of visible texts to click (e.g. a collection name → `Documents`
  → a filename → `Pages`).
- **Blob images** (page renders, figure crops) are fetched WITH the bearer and rendered via
  `URL.createObjectURL` (see `components/BlobImage.tsx`) — a plain `<img src="/api/v1/blobs/...">` would
  401. The script's `images` report is the regression signal: `blobObjectUrl` should equal `total` and
  `rawBlobsUrl` must be 0; any `unauthorized` entry means an auth-blind call slipped in.
- Ports: frontend `10046`, API `10040` (the frontend proxies `/api/v1` to it).
