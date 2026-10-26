#!/usr/bin/env bash
# One running dev stack per Orca worktree (template from the AI Dev Kit).
#
#   scripts/dev-stack.sh setup     worktree: port block, .env.worktree, database copied from main, stack up
#                                  main checkout: stack up on the usual ports
#   scripts/dev-stack.sh up        start (or update) the stack
#   scripts/dev-stack.sh rebuild   rebuild the images and restart, data kept
#   scripts/dev-stack.sh seed      worktree only: copy main's database into this one (only if empty)
#   scripts/dev-stack.sh url       print the address of the app
#   scripts/dev-stack.sh status    address, containers, then the logs (Orca "Stack" tab)
#   scripts/dev-stack.sh teardown  worktree only: stop, delete its containers and volumes, free the ports
#
# In a worktree, the app is at http://localhost:<first port of the block>, in Orca's browser of that
# worktree (Orca routes its traffic through the server). Published ports listen on 127.0.0.1 only.
# The compose files must read the variables below and must not set container_name or volume names.
#
# DocForge: the main checkout and every worktree run compose/compose.dev-cpu.yml +
# compose/overlays/compose.worktree.yml (no container names). Main is project "docforge" on the
# overlay's default ports (UI 10046, API 10040, mcp 10048, on 127.0.0.1); a worktree reads its
# project and ports from .env.worktree (UI = first port of the block, API = +1, mcp = +8). The UI
# is the Vite dev server (hot reload) proxying to the app; the API docs are at <API>/scalar. By
# default only the core services start (UI, app, worker, stores); opt in to the others with
# compose profiles (a COMPOSE_PROFILES set in the environment is honoured), e.g.
#   COMPOSE_PROFILES=models scripts/dev-stack.sh up          # + bge_server / paddle_server
#   COMPOSE_PROFILES=models,extras scripts/dev-stack.sh up   # + mcp
# The first start runs `npm ci` in the frontend container (a few minutes); `up --wait` only waits
# for it to be running (no healthcheck), so the page may need a moment after `setup` returns.
# Prod and the Makefile scenarios (make up-dev-cpu, ...) do not use this script or the overlay.
set -Eeuo pipefail

# --- Project settings: edit when adopting the template -------------------------------------------
PROJECT="docforge"                   # compose project of the main checkout: lowercase, digits, '-'
# Dev compose files (main checkout and worktrees), relative to the repository root.
COMPOSE_FILES=(-f compose/compose.dev-cpu.yml -f compose/overlays/compose.worktree.yml)
APP_SERVICE="docforge_frontend"      # service that serves the app (Vite UI), and its container port
APP_CONTAINER_PORT=5173
APP_PATH="/"                         # path of the page to open
# Database copied from main's stack into a new worktree (Postgres). Empty SEED_DB_SERVICE: no copy.
SEED_DB_SERVICE="docforge_postgres"
SEED_DB_USER="docforge"
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

worktree_slug() { # folder name -> lowercase, digits, '-' (at most 30 characters)
  local s
  s="$(basename "$ROOT" | tr '[:upper:]' '[:lower:]' | tr -c 'a-z0-9-' '-' | tr -s '-')"
  s="${s#-}"; s="${s%-}"; s="${s:0:30}"; s="${s%-}"
  printf '%s' "${s:-wt}"
}

compose() {
  local env_args=()
  [[ -f "$BASE_ENV_FILE" ]] && env_args+=(--env-file "$BASE_ENV_FILE")
  if ((IS_WORKTREE)); then
    docker compose "${env_args[@]}" --env-file "$ENV_FILE" "${COMPOSE_FILES[@]}" "$@"
  else
    COMPOSE_PROJECT_NAME="$PROJECT" docker compose "${env_args[@]}" "${COMPOSE_FILES[@]}" "$@"
  fi
}

# Writes .env.worktree (same port block on every call). Keeps SEEDED=1 once the copy is done.
write_env() {
  local base seeded=""
  [[ -x "$PORT_SLOT" ]] || die "dev-center only: $PORT_SLOT is missing (on another machine use the Makefile scenarios, see compose/README.md)"
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
  note "copying main's database into this worktree (read-only on main)"
  # The target is new and empty: "already exists" errors on the role and the default databases
  # are expected and harmless.
  docker exec "$src" pg_dumpall -U "$SEED_DB_USER" |
    compose exec -T "$SEED_DB_SERVICE" psql -q -U "$SEED_DB_USER" -d postgres >/dev/null
  printf 'SEEDED=1\n' >>"$ENV_FILE"
}

orca_comment() { # best effort: the address shows in Orca's worktree list
  local cli="${ORCA_CLI_COMMAND:-orca-ide}"
  command -v "$cli" >/dev/null 2>&1 || return 0
  "$cli" worktree set --worktree "path:$ROOT" --comment "App : $1" --json >/dev/null 2>&1 || true
}

up() { compose up -d --wait --wait-timeout 600 "$@"; }

case "${1:-}" in
  setup)
    if ((IS_WORKTREE)); then
      write_env
      seed
      up
      url="$(app_url)"
      orca_comment "$url"
      note "ready: $url (open it in this worktree's browser in Orca)"
    else
      up
      note "main stack up: $(app_url || echo '?')"
    fi
    ;;
  up) up ;;
  rebuild) up --build ;;
  seed) seed ;;
  url) app_url || exit 1 ;;
  status)
    app_url || true
    compose ps
    compose logs -f --tail 50
    ;;
  teardown)
    ((IS_WORKTREE)) || die "teardown never runs in the main checkout (it would delete main's data)"
    # Every profile, so containers started with COMPOSE_PROFILES=models/extras go too.
    if [[ -f "$ENV_FILE" ]]; then COMPOSE_PROFILES='*' compose down -v --remove-orphans; fi
    "$PORT_SLOT" release "$REPO_KEY" "$ROOT"
    rm -f "$ENV_FILE"
    note "stack, volumes and port block of this worktree removed"
    ;;
  *)
    sed -n '2,/^set -Eeuo/{/^set -Eeuo/d;s/^# \{0,1\}//;p}' "$0" >&2
    exit 2
    ;;
esac
