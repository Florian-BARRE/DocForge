---
name: dns-resolver-baked-at-creation
description: a container's /etc/resolv.conf ExtServers snapshot is fixed at container creation time, not live — explains flaky/inconsistent external DNS across sibling containers on the same VM
metadata:
  type: project
---

On this VM, Docker's embedded resolver (127.0.0.11) forwards to whatever the **host's** resolver
situation looked like at the moment a given container was created — captured once into that
container's `/etc/resolv.conf` as `ExtServers: [...]`. This is why sibling containers on the *same*
`rework_net`, created at different times, can have completely different external-DNS outcomes even
with identical compose config: one might show `ExtServers: [host(10.10.4.1)]` (working) and another
`# NO EXTERNAL NAMESERVERS DEFINED` (broken), because the host's own DNS/VPN state differed between
the two creation events.

**Why:** `docforge-rework-app` / `docforge-rework-worker` carry an explicit `dns: [1.1.1.1, 8.8.8.8]`
override in `docker-compose.rework.yml` specifically because of this flakiness (they call external
LLM/VLM/embed provider hosts). Verified live 2026-07-24: `docforge-rework-frontend` (no dns override)
currently has **zero** working external resolution (`getent hosts registry.npmjs.org` returns nothing)
while `docforge-rework-bge-server` (also no override) currently resolves `huggingface.co` fine — pure
container-creation-time luck, not a difference in compose.

**How to apply:** don't trust "it resolves DNS fine right now" as proof a service doesn't need the
`dns:` pin — re-test after any container recreation, or just apply the pin proactively to any service
that touches an external hostname (frontend's `npm install`, bge_server's first-boot HF download,
future MCP/provider calls). A service that currently works may break silently on its next recreation
with zero compose change. See [[v1-audit-open-gaps]] for the specific services still missing the pin.
