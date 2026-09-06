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
    compose.telemetry.yml              # OPTIONAL — Prometheus + Loki + Promtail + Grafana (add-on)
  compose.dev-cpu.yml  compose.dev-gpu.yml  compose.prod-cpu.yml  compose.prod-gpu.yml   # ready-made scenario files
  README.md                  # this file

services/telemetry/          # config for the telemetry overlay (prometheus.yml, loki/promtail
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

`--profile full` is mandatory in every scenario — app/worker/frontend/mcp live under it (omitting
it starts only the data-plane stores).

## Add-ons (layered with an extra `-f`, never baked into a scenario file)

```bash
# TLS front door (Caddy, auto-HTTPS) — needs DOCFORGE_DOMAIN / DOCFORGE_ACME_EMAIL in the
# project-root .env:
docker compose -f compose/compose.prod-cpu.yml -f compose/overlays/compose.proxy.yml --profile full up -d

# Observability stack (Prometheus/Loki/Promtail/Grafana):
docker compose -f compose/compose.prod-cpu.yml -f compose/overlays/compose.telemetry.yml --profile full up -d

# Both, on any scenario:
docker compose -f compose/compose.prod-gpu.yml -f compose/overlays/compose.proxy.yml -f compose/overlays/compose.telemetry.yml --profile full up -d
```

## Makefile targets (repo root)

`up-prod-cpu` / `up-prod-gpu` / `up-dev-cpu` / `up-dev-gpu`, each with a `-proxy` and
`-telemetry` variant (e.g. `up-dev-gpu-telemetry`), plus `down-*` and `logs`. Run
`make config-check-all` after touching anything under `compose/` — it validates every scenario
alone and combined with every add-on combination.

## The telemetry stack

Opt-in via `compose/overlays/compose.telemetry.yml`. Four containers, **no `profiles:` gate** (unlike
app/worker/frontend/mcp, which require `--profile full`) — they start unconditionally whenever
the overlay is included, so combining it with `--profile full` still starts the rest of the
stack exactly as before.

| Service | Role | Host port |
|---|---|---|
| `grafana` | Provisioned with both datasources + a starter "DocForge — API & Worker Overview" dashboard (request rate, p95 latency, error rate, arq queue depth, job counts, live workers). | `10050` |
| `prometheus` | Scrapes `docforge_app:8000/metrics` **over `docforge_net`** — not the published host port. | `10051` |
| `loki` | Log storage/index, receives from promtail. | `10052` |
| `promtail` | Tails every container's Docker log (`docker_sd_configs` against the read-only `docker.sock` + `/var/lib/docker/containers` mounts) and ships to loki. | — (no host port) |

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
  file's own header comment for the explicit reasoning.

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
