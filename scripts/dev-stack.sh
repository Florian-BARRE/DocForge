#!/usr/bin/env bash
# One running dev stack per Orca worktree (template from the AI Dev Kit, ~/.aidk/kit/platforms/linux/templates/project).
#
#   scripts/dev-stack.sh prepare           worktree: port block, .env.worktree, images built and pulled;
#                                          nothing started (aidk stack setup, when .aidk/project.toml has a [stack])
#   scripts/dev-stack.sh setup             prepare, then the whole stack up, database copied from main first
#                                          (main checkout: the whole stack up on the usual ports)
#   scripts/dev-stack.sh up [SERVICE...]   start these and what they depend on (depends_on), or the whole stack;
#                                          a worktree copies main's database first when the database is among them
#   scripts/dev-stack.sh stop SERVICE...   stop these services, data kept
#   scripts/dev-stack.sh rebuild [SERVICE...]  rebuild the images and restart (the running ones without a
#                                          name), data kept
#   scripts/dev-stack.sh down              stop the whole stack, data kept
#   scripts/dev-stack.sh seed              worktree only: copy main's database into this one (only if empty)
#   scripts/dev-stack.sh deps SERVICE...   what `up SERVICE...` starts (the services and their depends_on)
#   scripts/dev-stack.sh url               print the address of the app
#   scripts/dev-stack.sh ps                the address and the containers
#   scripts/dev-stack.sh status            the same, then follows the logs (Orca "Stack" tab)
#   scripts/dev-stack.sh teardown          worktree only: stop, delete its containers, volumes and built
#                                          images, free the ports
#
# In a worktree, the app is at http://localhost:<first port of the block>, in Orca's browser of that
# worktree (Orca routes its traffic through the server). Published ports listen on 127.0.0.1 only.
# The compose files must read the variables below and must not set container_name or volume names.
# Which services a worktree starts, and when, is declared in .aidk/project.toml ([stack]: aidk stack up NAME).
#
# DocForge: the main checkout and every worktree run compose/compose.dev-cpu.yml +
# compose/overlays/compose.worktree.yml (no container names). Main is project "docforge" on the
# overlay's default ports (UI 10046, API 10040, mcp 10048, on 127.0.0.1); a worktree reads its
# project and ports from .env.worktree (UI = first port of the block, API = +1, mcp = +8). The UI
# is the Vite dev server (hot reload) proxying to the app; the API docs are at <API>/scalar.
# A worktree starts nothing at setup (prepare); `aidk stack up frontend` starts the UI, the app and
# the stores. A service behind a compose profile (bge_server / paddle_server: models, mcp: extras)
# starts when named (`up docforge_mcp`, `aidk stack up mcp`); a COMPOSE_PROFILES set in the
# environment is honoured too, e.g. COMPOSE_PROFILES=models scripts/dev-stack.sh up.
# The first start runs `npm ci` in the frontend container (a few minutes); `up --wait` only waits
# for it to be running (no healthcheck), so the page may need a moment after `up` returns.
# Prod and the Makefile scenarios (make up-dev-cpu, ...) do not use this script or the overlay.
set -Eeuo pipefail

# --- Project settings: edit when adopting the template -------------------------------------------
PROJECT="docforge"                   # compose project of the main checkout: lowercase, digits, '-'
# Dev compose files (main checkout and worktrees), relative to the repository root.
COMPOSE_FILES=(-f compose/compose.dev-cpu.yml -f compose/overlays/compose.worktree.yml)
APP_SERVICE="docforge_frontend"      # service that serves the app (Vite UI), and its container port
APP_CONTAINER_PORT=5173
APP_PATH="/"                         # path of the page to open
# false: a worktree builds its images on its first `aidk stack up` (several GB for app, worker, mcp,
# bge and paddle: built at prepare, they made Orca's setup outlast the agent's start).
PREPARE_IMAGES=false                 # true: prepare builds and pulls the images, so a first start is quick
# Database copied from main's stack into a new worktree (Postgres). Empty SEED_DB_SERVICE: no copy.
SEED_DB_SERVICE="docforge_postgres"
SEED_DB_USER="docforge"
SEED_DB_NAME="docforge"              # database checked for tables before a copy (POSTGRES_DB)
# Compose interpolation file of the repository (POSTGRES_DSN with the local dev password). Compose
# does not read it on its own (the project directory is compose/), so it is passed explicitly,
# before .env.worktree (the later file wins).
BASE_ENV_FILE=.env
# Variables written to .env.worktree for a worktree, besides COMPOSE_PROJECT_NAME / BIND_ADDR /
# PORT_BASE / APP_PORT. Map the other published ports inside the block (PORT_BASE + 1 … + 99).
# The worker's cron jobs are local housekeeping on the worktree's own stores (nothing is sent
# outside the stack), so no switch is needed to turn them off.
worktree_extra_env() { # $1: first port of the block
  printf 'API_PORT=%s\nMCP_PORT=%s\n' "$(($1 + 1))" "$(($1 + 8))"
}
# --------------------------------------------------------------------------------------------------

# The kit's port-slot tool, in the account (AIDK_PORT_SLOT overrides it).
PORT_SLOT="${AIDK_PORT_SLOT:-$HOME/.aidk/bin/aidk-port-slot}"
ENV_FILE=.env.worktree

die() { echo "dev-stack: $*" >&2; exit 1; }
note() { echo "dev-stack: $*"; }

[[ "$PROJECT" =~ ^[a-z0-9][a-z0-9-]{0,40}$ ]] || die "PROJECT must be lowercase letters, digits and '-'"
ROOT="$(git rev-parse --show-toplevel)" || die "not inside a git checkout"
cd "$ROOT"
GIT_DIR_ABS="$(git rev-parse --path-format=absolute --git-dir)"
GIT_COMMON_ABS="$(git rev-parse --path-format=absolute --git-common-dir)"
if [[ "$GIT_DIR_ABS" != "$GIT_COMMON_ABS" ]]; then IS_WORKTREE=1; else IS_WORKTREE=0; fi
REPO_KEY="$(basename "$(dirname "$GIT_COMMON_ABS")")"   # repository folder of the main checkout
BASE_ENV_ARGS=()
[[ -f "$BASE_ENV_FILE" ]] && BASE_ENV_ARGS+=(--env-file "$BASE_ENV_FILE")

worktree_slug() { # folder name -> lowercase, digits, '-' (at most 30 characters)
  local s
  s="$(basename "$ROOT" | tr '[:upper:]' '[:lower:]' | tr -c 'a-z0-9-' '-' | tr -s '-')"
  s="${s#-}"; s="${s%-}"; s="${s:0:30}"; s="${s%-}"
  printf '%s' "${s:-wt}"
}

compose() {
  if ((IS_WORKTREE)); then
    [[ -f "$ENV_FILE" ]] || write_env  # the worktree's port block, before anything reads it
    docker compose "${BASE_ENV_ARGS[@]}" --env-file "$ENV_FILE" "${COMPOSE_FILES[@]}" "$@"
  else
    # The main checkout keeps its usual ports, on loopback too: Orca's browser reaches them through
    # the server, the LAN never does (a compose file may default to every interface for prod).
    BIND_ADDR="${BIND_ADDR:-127.0.0.1}" COMPOSE_PROJECT_NAME="$PROJECT" docker compose "${BASE_ENV_ARGS[@]}" \
      "${COMPOSE_FILES[@]}" "$@"
  fi
}

# Checked only where a port block is acquired, so teardown, down and ps still run without the tool.
need_port_slot() {
  [[ -x "$PORT_SLOT" ]] ||
    die "the AI Dev Kit's port-slot tool is missing ($PORT_SLOT): a worktree needs it for its port block; install the kit or set AIDK_PORT_SLOT"
}

# Writes .env.worktree (same port block on every call). Keeps SEEDED=1 once the copy is done.
write_env() {
  local base seeded=""
  need_port_slot
  base="$("$PORT_SLOT" acquire "$REPO_KEY" "$ROOT")"
  [[ -f "$ENV_FILE" ]] && grep -qx 'SEEDED=1' "$ENV_FILE" && seeded="SEEDED=1"
  {
    printf '# Written by scripts/dev-stack.sh for this worktree only (gitignored).\n'
    printf 'COMPOSE_PROJECT_NAME=%s-%s\n' "$PROJECT" "$(worktree_slug)"
    printf 'BIND_ADDR=127.0.0.1\nPORT_BASE=%s\nAPP_PORT=%s\n' "$base" "$base"
    worktree_extra_env "$base"
    [[ -z "$seeded" ]] || printf '%s\n' "$seeded"
  } >"$ENV_FILE.tmp"
  mv -f "$ENV_FILE.tmp" "$ENV_FILE"
}

env_value() { sed -n "s/^$1=//p" "$ENV_FILE" | tail -n 1; }

app_url() {
  if ((IS_WORKTREE)); then
    [[ -f "$ENV_FILE" ]] || { echo "dev-stack: no $ENV_FILE yet: run scripts/dev-stack.sh setup" >&2; return 1; }
    printf 'http://localhost:%s%s\n' "$(env_value APP_PORT)" "$APP_PATH"
  else
    local hostport
    hostport="$(compose port "$APP_SERVICE" "$APP_CONTAINER_PORT" 2>/dev/null | tail -n 1)"
    [[ -n "$hostport" ]] || { echo "dev-stack: $APP_SERVICE does not publish $APP_CONTAINER_PORT (stack down?)" >&2; return 1; }
    printf 'http://localhost:%s%s\n' "${hostport##*:}" "$APP_PATH"
  fi
}

# Copies main's database into this worktree's, once, and only into an empty database.
seed() {
  ((IS_WORKTREE)) || die "seed runs in a worktree, never in the main checkout"
  [[ -n "$SEED_DB_SERVICE" ]] || { note "no database to copy (SEED_DB_SERVICE empty)"; return 0; }
  if grep -qx 'SEEDED=1' "$ENV_FILE"; then note "database already copied from main"; return 0; fi
  local src
  src="$(docker ps -q --filter "label=com.docker.compose.project=$PROJECT" \
    --filter "label=com.docker.compose.service=$SEED_DB_SERVICE" | head -n 1)"
  compose up -d --wait --wait-timeout 300 "$SEED_DB_SERVICE"
  if [[ -z "$src" ]]; then
    note "WARNING: main's stack ($PROJECT) is not running: this worktree starts with an empty database"
    return 0
  fi
  # SEEDED=1 is lost if .env.worktree is deleted by hand: never restore over existing tables.
  local tables
  tables="$(compose exec -T "$SEED_DB_SERVICE" psql -U "$SEED_DB_USER" -d "$SEED_DB_NAME" -tAc \
    "select count(*) from information_schema.tables where table_schema = 'public'" 2>/dev/null || true)"
  if [[ "${tables//[[:space:]]/}" =~ ^[1-9][0-9]*$ ]]; then
    note "this worktree's database already has tables: not copying"
    return 0
  fi
  note "copying main's database into this worktree (read-only on main)"
  # The target is new and empty: "already exists" errors on the role and the default databases
  # are expected and harmless.
  docker exec "$src" pg_dumpall -U "$SEED_DB_USER" |
    compose exec -T "$SEED_DB_SERVICE" psql -q -U "$SEED_DB_USER" -d postgres >/dev/null
  printf 'SEEDED=1\n' >>"$ENV_FILE"
}

# The services `up SERVICE...` starts: these and, through depends_on, what they depend on (one per line).
deps() {
  # --profile '*': a service behind a profile (mcp: extras) starts when named, so its depends_on count too.
  # --no-env-resolution: a missing env file must not break the list (need_env_files reports it).
  compose --profile '*' config --no-env-resolution --format json | python3 -I -c '
import json, sys
services = json.load(sys.stdin).get("services") or {}
todo, seen = list(sys.argv[1:]), set()
while todo:
    name = todo.pop()
    if name in seen or name not in services:
        continue
    seen.add(name)
    todo += list(services[name].get("depends_on") or [])
print("\n".join(sorted(seen)))' "$@"
}

# Stops with the list of the env files (env_file) that SERVICE... and what they depend on need (every
# active service without a name) and that do not exist, each with the template to copy. Compose would
# stop at the first one with a bare "env file … not found".
need_env_files() {
  local profiles=() missing=() file msg
  (($#)) && profiles=(--profile '*')
  mapfile -t missing < <(compose "${profiles[@]}" config --no-env-resolution --format json | python3 -I -c '
import json, os, sys
services = json.load(sys.stdin).get("services") or {}
todo, seen = list(sys.argv[2:]) or list(services), set()
while todo:
    name = todo.pop()
    if name in seen or name not in services:
        continue
    seen.add(name)
    todo += list(services[name].get("depends_on") or [])
missing = set()
for name in seen:
    for entry in services[name].get("env_file") or []:
        if isinstance(entry, str):
            entry = {"path": entry}
        if entry.get("required", True) and not os.path.exists(entry["path"]):
            missing.add(os.path.relpath(entry["path"], sys.argv[1]))
print("\n".join(sorted(missing)))' "$ROOT" "$@")
  [[ -n "${missing[*]}" ]] || return 0
  msg="missing env files, which the compose files read:"
  for file in "${missing[@]}"; do
    [[ -n "$file" ]] || continue
    if [[ -f "$file.example" ]]; then
      msg+=$'\n'"  $file: copy its template (cp $file.example $file), then fill it in"
    else
      msg+=$'\n'"  $file"
    fi
  done
  die "$msg"
}

prepare() {
  ((IS_WORKTREE)) && write_env
  [[ "$PREPARE_IMAGES" == true ]] || return 0
  # A broken Dockerfile on a branch must not block the worktree: its agent is the one to fix it.
  note "building and pulling the images (nothing is started)"
  compose build --quiet || note "WARNING: an image did not build: up will show why"
  compose pull --quiet --ignore-buildable 2>/dev/null || note "WARNING: an image could not be pulled: up will try again"
}

# Starts SERVICE... (all without a name): the worktree's port block first, main's database copied when the
# database is among what starts. BUILD=1: rebuild the images.
bring_up() {
  local build="$1"; shift
  ((IS_WORKTREE)) && [[ ! -f "$ENV_FILE" ]] && write_env
  need_env_files "$@"
  if ((IS_WORKTREE)); then
    if [[ -n "$SEED_DB_SERVICE" ]] && ! grep -qx 'SEEDED=1' "$ENV_FILE" &&
        { (($# == 0)) || deps "$@" | grep -qx "$SEED_DB_SERVICE"; }; then
      seed
    fi
  fi
  if ((build)); then
    compose up -d --build --wait --wait-timeout 600 "$@"
  else
    compose up -d --wait --wait-timeout 600 "$@"
  fi
  if ((IS_WORKTREE)) && { (($# == 0)) || deps "$@" | grep -qx "$APP_SERVICE"; }; then
    url="$(app_url)" && orca_comment "$url" && note "ready: $url (open it in this worktree's browser in Orca)"
  fi
  return 0
}

# Teardown: deletes the images this worktree built (${COMPOSE_PROJECT_NAME}-<name>:dev, several GB each).
# The names come from the compose config, not a glob: a worktree "bge" must never match main's
# docforge-bge-server:dev. Pulled images and main's docforge-*:dev stay; a missing image is skipped.
remove_worktree_images() {
  [[ -f "$ENV_FILE" ]] || return 0
  local project images
  project="$(env_value COMPOSE_PROJECT_NAME)"
  [[ "$project" == "$PROJECT"-* ]] || { note "WARNING: unexpected project '$project': images kept"; return 0; }
  mapfile -t images < <(timeout 20 docker compose "${BASE_ENV_ARGS[@]}" --env-file "$ENV_FILE" \
    "${COMPOSE_FILES[@]}" --profile '*' config --images --no-env-resolution 2>/dev/null |
    grep -E "^${project}-[a-z0-9_.-]+:dev\$" | sort -u)
  ((${#images[@]})) || return 0
  local present=() image
  for image in "${images[@]}"; do
    docker image inspect "$image" >/dev/null 2>&1 && present+=("$image")
  done
  ((${#present[@]})) || return 0
  note "removing this worktree's images: ${present[*]}"
  timeout 30 docker image rm "${present[@]}" >/dev/null || note "WARNING: some images were not removed (in use?)"
}

orca_comment() { # best effort: the address shows in Orca's worktree list
  local cli="${ORCA_CLI_COMMAND:-orca-ide}"
  command -v "$cli" >/dev/null 2>&1 || return 0
  "$cli" worktree set --worktree "path:$ROOT" --comment "App : $1" --json >/dev/null 2>&1 || true
}

case "${1:-}" in
  prepare) prepare ;;
  setup)
    if ((IS_WORKTREE)); then
      write_env
      bring_up 0
    else
      bring_up 0
      note "main stack up: $(app_url || echo '?')"
    fi
    ;;
  up) shift; bring_up 0 "$@" ;;
  rebuild)
    shift
    if (($# == 0)); then  # the running services only, a profiled one (models, extras) included
      mapfile -t running < <(compose --profile '*' ps --services --status running)
      ((${#running[@]})) || { note "nothing runs: up SERVICE... first"; exit 0; }
      set -- "${running[@]}"
    fi
    bring_up 1 "$@"
    ;;
  stop) shift; (($#)) || die "stop needs the services to stop (down stops the whole stack)"; compose stop "$@" ;;
  down) compose --profile '*' down --remove-orphans ;;  # no -v: data kept
  deps) shift; (($#)) || die "deps needs services"; need_env_files "$@"; deps "$@" ;;
  seed) seed ;;
  url) app_url || exit 1 ;;
  ps)
    app_url || true
    compose ps
    ;;
  status)
    app_url || true
    compose ps
    compose logs -f --tail 50
    ;;
  teardown)
    ((IS_WORKTREE)) || die "teardown never runs in the main checkout (it would delete main's data)"
    # --profile '*': services behind a compose profile (pgAdmin…) and their volumes go too. Orca gives the
    # archive script 120 s and keeps the worktree when it fails: 5 s for the containers to stop, a kill
    # when that is not enough, everything bounded well under the limit.
    if [[ -f "$ENV_FILE" ]]; then
      if ! timeout 60 docker compose "${BASE_ENV_ARGS[@]}" --env-file "$ENV_FILE" "${COMPOSE_FILES[@]}" --profile '*' down -v \
          --remove-orphans --timeout 5; then
        note "the stack did not stop in time: killing it"
        timeout 15 docker compose "${BASE_ENV_ARGS[@]}" --env-file "$ENV_FILE" "${COMPOSE_FILES[@]}" --profile '*' kill || true
        timeout 20 docker compose "${BASE_ENV_ARGS[@]}" --env-file "$ENV_FILE" "${COMPOSE_FILES[@]}" --profile '*' down -v \
          --remove-orphans --timeout 0 || die "the stack is still there: docker compose ps, then teardown again"
      fi
    fi
    remove_worktree_images
    if [[ -x "$PORT_SLOT" ]]; then
      "$PORT_SLOT" release "$REPO_KEY" "$ROOT"
    else
      note "WARNING: the port-slot tool is missing: this worktree's port block is not released"
    fi
    rm -f "$ENV_FILE"
    note "stack, volumes, images and port block of this worktree removed"
    ;;
  *)
    sed -n '2,/^set -Eeuo/{/^set -Eeuo/d;s/^# \{0,1\}//;p}' "$0" >&2
    exit 2
    ;;
esac
