# DocForge — `compose/`

Per-usage-scenario Docker Compose layout. Every file has a header comment stating WHEN to use
it — this README is the index + the usage matrix + the Makefile targets.

## Layout

```
compose/
  compose.base.yml                 # ALL services + volumes + network — never used alone
  overlays/
    compose.gpu.yml                 # -gpu images + `gpus: all` for worker/bge_server/paddle_server
    compose.dev.yml                  # local build + source mounts + hot reload + Vite frontend
    compose.proxy.yml                 # OPTIONAL — Caddy TLS front door (add-on, not baked into scenarios)
    compose.telemetry.yml              # OPTIONAL — Prometheus + Loki + Alloy + Grafana (add-on)
    compose.worktree.yml               # dev-center dev stack (main checkout + each git worktree) — via scripts/dev-stack.sh only
  compose.dev-cpu.yml  compose.dev-gpu.yml  compose.prod-cpu.yml  compose.prod-gpu.yml   # ready-made scenario files
  README.md                  # this file

services/telemetry/          # config for the telemetry overlay (prometheus.yml, loki/alloy
                              # configs, grafana provisioning + starter dashboard) — a SIBLING of
                              # compose/ at the repo root, not a subdirectory of it (same home as
                              # services/caddy, services/docforge, etc.)
```

The repo-root `docker-compose.yml` is a thin `include: [compose/compose.prod-cpu.yml]` — a bare
`docker compose --profile full up -d` at the repo root still gets you prod-CPU, unchanged from
before this reorg.

## Usage matrix

| Scenario | Command | When |
|---|---|---|
| Prod CPU (default) | `docker compose -f compose/compose.prod-cpu.yml --profile full up -d` | Normal CPU production/staging. Also the repo-root default. |
| Prod GPU | `docker compose -f compose/compose.prod-gpu.yml --profile full up -d` | Production/staging on a GPU host (NVIDIA Container Toolkit required). |
| Dev CPU | `docker compose -f compose/compose.dev-cpu.yml --profile full up -d --build` | Local development, CPU machine (the common case). |
| Dev GPU | `docker compose -f compose/compose.dev-gpu.yml --profile full up -d --build` | Local development on a GPU-equipped machine. |
| Dev-center dev stack | `aidk stack up NAME` / `rebuild` / `down` through `scripts/dev-stack.sh` (layers `compose/overlays/compose.worktree.yml` on `compose.dev-cpu.yml`) | The dev center: the main checkout and each git worktree, side by side on one shared CPU host. **Never prod.** See [the per-worktree dev stack](#the-per-worktree-dev-stack). |

`--profile full` is mandatory in every Makefile/scenario command (the dev-center stack resets
profiles, see below) — app/worker/frontend/mcp live under it (omitting it starts only the
data-plane stores).

**On the dev center, never use `make up-*` / `down-*`**: they use the fixed compose project
`docforge` and fixed container names, so run from a worktree they would take over (or tear down)
main's stack. Use `scripts/dev-stack.sh` only. Elsewhere (a contributor's machine) the Makefile
scenarios remain the way to run DocForge.

## Add-ons (layered with an extra `-f`, never baked into a scenario file)

```bash
# TLS front door (Caddy, auto-HTTPS) — needs DOCFORGE_DOMAIN / DOCFORGE_ACME_EMAIL in the
# project-root .env:
docker compose -f compose/compose.prod-cpu.yml -f compose/overlays/compose.proxy.yml --profile full up -d

# Observability stack (Prometheus/Loki/Alloy/Grafana):
docker compose -f compose/compose.prod-cpu.yml -f compose/overlays/compose.telemetry.yml --profile full up -d

# Both, on any scenario:
docker compose -f compose/compose.prod-gpu.yml -f compose/overlays/compose.proxy.yml -f compose/overlays/compose.telemetry.yml --profile full up -d
```

## Makefile targets (repo root)

`up-prod-cpu` / `up-prod-gpu` / `up-dev-cpu` / `up-dev-gpu`, each with a `-proxy` and
`-telemetry` variant (e.g. `up-dev-gpu-telemetry`), plus `down-*` and `logs`. Run
`make config-check-all` after touching anything under `compose/` — it validates every scenario
alone and combined with every add-on combination, plus the worktree overlay on `compose.dev-cpu.yml`
with no profile and with every profile.

## The per-worktree dev stack

`compose/overlays/compose.worktree.yml` is the dev-center dev stack: the main checkout and every git
worktree each run their own stack (own containers, volumes, network and host ports per compose
project) on one shared host. It is layered with a plain `-f` on top of `compose.dev-cpu.yml`,
**always through `scripts/dev-stack.sh`** — never in prod, and the Makefile scenarios
(`make up-dev-cpu`, ...) do not use it. On the dev center, never run `make up-*` / `down-*` at all
(main checkout or worktree): they use the fixed project `docforge` and fixed container names, so
they would take over main's stack — `scripts/dev-stack.sh` only.

A new worktree starts nothing: Orca's setup (`aidk stack setup`, i.e. `scripts/dev-stack.sh prepare`)
only writes its port block and `.env.worktree` (seconds: no image is built or pulled). The first
`aidk stack up` of a worktree builds the images it needs, so the first start of `app`, `worker`,
`mcp`, `bge` or `paddle` is slow (several GB, minutes); later starts reuse them. Each stack names
the images it builds after its compose project, `${COMPOSE_PROJECT_NAME:-docforge}-<name>:dev`: main
keeps `docforge-app:dev` and the like, a worktree gets `docforge-<slug>-app:dev`, so a rebuild in one
worktree never replaces the image main or another worktree runs; the worktree's teardown deletes
the images it built (never main's nor a pulled one). The agent starts only
what its work needs; the services are declared in `[stack]` of `.aidk/project.toml` (each names its
compose service, its `needs` and its code `paths`), and a worktree copies main's database the first
time postgres starts:

```bash
aidk stack status                                 # declared services, what runs, what would start
aidk stack up frontend                            # docforge_frontend + docforge_app + qdrant + postgres/redis/seaweedfs
aidk stack up worker                              # docforge_worker + qdrant + gotenberg + the stores
aidk stack up mcp                                 # docforge_mcp (profile extras) + the app
aidk stack up bge paddle                          # bge_server / paddle_server (profile models)
aidk stack rebuild NAME | browse | down           # rebuild an image, open the UI in Orca, stop
aidk stack release                                # worktree removal (Orca's archive): containers, volumes, images, ports
```

`scripts/dev-stack.sh up SERVICE...` (compose names) and `setup` (everything not behind a profile)
still work by hand; `url`, `ps`, `status` and `teardown` too.

**The UI is the Vite frontend** (`docforge_frontend`, hot reload), the "app" of
`scripts/dev-stack.sh` (`url` prints it): it proxies `/api`, `/capabilities` and `/health` to the
app service (`VITE_API_PROXY_TARGET=http://docforge_app:8000`). The API is published too, on the
next port, with its docs at `/scalar`; its `/` is 404 in dev because the source bind-mount hides the
image's built UI. The frontend has no healthcheck, so `up --wait` only waits for it to be running:
its first start runs `npm ci` in the container (a few minutes) before Vite answers.

**Profiles** (no `--profile full` here — the overlay resets app/worker's profile). Naming a service
behind a profile starts it (`aidk stack up mcp`); `COMPOSE_PROFILES` in the environment is honoured too:

| Profile | Services |
|---|---|
| core (none) | `docforge_frontend` (Vite UI), `docforge_app`, `docforge_worker`, postgres, redis, qdrant, seaweedfs, gotenberg |
| `models` | `docforge_bge_server`, `docforge_paddle_server` (heavy CPU model hosts — check free memory first) |
| `extras` | `docforge_mcp` |

mineru / dots_ocr keep their GPU-only opt-in profiles.

**Ports**: only the three a browser needs are published, all on `${BIND_ADDR:-127.0.0.1}` —
UI (frontend) `APP_PORT` (`10046` in main), API (app) `API_PORT` (`10040`), mcp `MCP_PORT`
(`10048`). A worktree gets its own port block, written by the script to the gitignored
`.env.worktree` (with `COMPOSE_PROJECT_NAME`): UI = first port of the block, API = +1, mcp = +8. The data-plane stores publish nothing; services reach each other by
service name / alias over the project network.

**What else differs from `compose.dev-cpu.yml`**:

- no `container_name` (`!reset null`) — containers are named `<project>-<service>-N`, so stacks never collide;
- S3 endpoint `http://seaweedfs:8333`: botocore rejects `_` in hostnames and the base file's hyphenated
  `container_name` is gone, so `docforge_seaweedfs` gets a project-scoped network alias `seaweedfs`;
- the worker's HuggingFace cache is the project's named volume, not the host's shared cache;
- startup order survives a host/VM reboot (the Docker daemon then restarts every container at once and
  ignores `depends_on`): seaweedfs is healthy only once its S3 gateway (8333) answers too, and app and
  worker wait for `seaweedfs:8333` (up to 180 s) before exec'ing their usual dev command;
- lower memory ceilings (app 1g, worker 3g, postgres 1g with `shared_buffers=256MB`, redis 256m with
  `maxmemory 160mb`, qdrant 1g, seaweedfs 512m, gotenberg 1g, frontend 1g; `models`: bge 4g, paddle 6g).
  The worker's 3g cap suits the shared host, but a large OCR-heavy ingestion can peak at 2-4 GiB
  and may be OOM-killed in a dev stack: raise the worker's limit locally if you need such a run.
  The worker's parse RSS watchdog is pinned to `WORKER_PARSE_RSS_LIMIT_MB=2560` (the auto value of a
  3g cap, 1536 MiB, fails a single scanned page); main and prod keep the auto formula.

**Env files**: the project directory is `compose/`, so compose does not read the repo-root `.env` on
its own — the script passes `--env-file .env` explicitly (then `--env-file .env.worktree` in a
worktree, the later file wins). Its relative paths (the worker's source mounts) resolve against
`compose/`, hence a single `../`. `make config-check-all` validates the overlay with no profile and
with every profile.

**`services/docforge/s3_config.json` must be readable by the container** (mode 644): with rootless
Docker and a private checkout directory, a 600 file is unreadable inside seaweedfs, its S3 gateway
dies with "permission denied" and the app fails at startup.

## The telemetry stack

Opt-in via `compose/overlays/compose.telemetry.yml`. Four containers, **no `profiles:` gate** (unlike
app/worker/frontend/mcp, which require `--profile full`) — they start unconditionally whenever
the overlay is included, so combining it with `--profile full` still starts the rest of the
stack exactly as before.

| Service | Role | Host port |
|---|---|---|
| `grafana` | Provisioned with both datasources + a starter "DocForge — API & Worker Overview" dashboard (request rate, p95 latency, error rate, arq queue depth, job counts, live workers). | `10050` |
| `prometheus` | Scrapes `docforge_app:8000/metrics` **over `docforge_net`** — not the published host port. | `10051` |
| `loki` | Log storage/index, receives from alloy. | `10052` |
| `alloy` | Tails every container's Docker log (`discovery.docker` against the read-only `docker.sock` + `/var/lib/docker/containers` mounts) and ships to loki. | — (no host port) |

Chosen because `10040`–`10049` are already used by the core stack (see the ports table in
`docs/configuration.md`) — `10050`–`10052` are the next free slots inside the VM firewall's
`10000`–`11000` range.

**`/metrics` is unauthenticated** (see `METRICS_ENABLED` in `docs/configuration.md`) — this is
exactly why Prometheus reaches the app over the internal `docforge_net` (`docforge_app:8000`)
rather than through a published port. Keep the telemetry stack itself off any public interface
too (Grafana/Prometheus/Loki host ports are for an operator/VPN, not the public internet) —
front Grafana with `compose/overlays/compose.proxy.yml` or an OS firewall rule if you need remote access.

**Grafana admin password**: lives in `services/telemetry/.env` (`GF_SECURITY_ADMIN_USER` /
`GF_SECURITY_ADMIN_PASSWORD` — Grafana's own env vars, injected via `env_file`), the same
discoverable per-service config home as `services/caddy` and `services/docforge` — **not** the
project-root `.env`. Copy `services/telemetry/.env.example` → `.env` and change the password
before exposing Grafana beyond localhost/an operator VPN. Open Grafana at
`http://localhost:10050` (or your host's address), user `admin`.

## The `../` path note

This splits along the SAME line as the merge-order gotcha below: `include:`-ed files
(`compose.base.yml`, `overlays/compose.dev.yml`, `overlays/compose.gpu.yml`) resolve their relative paths **relative to
that file's own directory**, while `-f`-layered add-ons (`overlays/compose.proxy.yml`,
`overlays/compose.telemetry.yml`) resolve relative to the **project directory** — the first `-f` file's
own dir, i.e. `compose/` in every scenario file's invocation. Concretely:

- `compose.base.yml` lives in `compose/`, `include:`-ed → its paths use `../` (e.g.
  `../services/docforge/.env`).
- `overlays/compose.dev.yml` / `overlays/compose.gpu.yml` live one level deeper, in `compose/overlays/`, and are
  also `include:`-ed → their paths use `../../` for anything under the repo root
  (`../../src/docforge`, `../../services/caddy/Caddyfile`).
- `overlays/compose.proxy.yml` / `overlays/compose.telemetry.yml` also live in `compose/overlays/`, but are
  **never `include:`-ed** — always layered with a plain `-f` on top of an already-assembled
  scenario file — so despite living in the same directory as compose.dev.yml/compose.gpu.yml, their paths
  resolve like `compose.base.yml`'s: a single `../` from `compose/` (e.g.
  `../services/telemetry/prometheus.yml`, `../services/caddy/Caddyfile`), NOT `../../`. See each
  file's own header comment for the explicit reasoning. `overlays/compose.worktree.yml` is layered the
  same way, so its worker source mounts use a single `../` too (`../src/docforge/worker`).

Validated with `docker compose -f <file> config` — it prints every resolved absolute path; that's
the check to re-run after touching any path in this tree.

## The `include:` merge-order gotcha (read this before adding a new overlay)

Verified on this repo's Compose version (`v5.1.1`): when two `include:`d files define the **same
service**, the merge picks, for any leaf both files set (a scalar like `image:`, or a
list/map entry keyed by target like a `volumes:` mount), the value from whichever file is listed
**first** — the opposite of `-f`'s last-wins. `-f` stacking is unaffected (confirmed correct
last-wins); only `include:` behaves this way. This is why every scenario file's `include:` list
puts the most-specific overlay **first** and `compose.base.yml` **last** (e.g. `compose.dev-gpu.yml`: `compose.gpu.yml`,
then `compose.dev.yml`, then `compose.base.yml`) — see each scenario file's own header comment and
`compose/overlays/compose.gpu.yml`'s header for the full reproduction and reasoning. `compose.proxy.yml` and
`compose.telemetry.yml` are never `include:`d (always layered with a plain `-f` on top of an already-
assembled scenario file), so they don't need this ordering trick.

If you add a new overlay that touches a service `compose.base.yml` (or another overlay) also defines,
list it **before** the file(s) it needs to override in every scenario file that combines them,
and re-run `make config-check-all` to prove the resolved values are what you expect — `config -q`
only proves the YAML is valid, not that the merge picked the value you intended.
