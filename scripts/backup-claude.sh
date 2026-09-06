#!/usr/bin/env bash
# ====== Code Summary ======
# Snapshot the LOCAL, gitignored .claude/ agent infrastructure to the VM backup dir.
#
# Why this exists (audit finding, HAUTE): the repo is PUBLIC, so .claude/ (agents, rules, commands,
# agent-memory) is deliberately gitignored — never published. But that left it as a SINGLE unversioned
# copy, which was silently lost once. This script gives it a durable, repeatable, versioned-by-timestamp
# backup WITHOUT exposing it in the public repo. Run it from a cron/hook or by hand after meaningful
# .claude/ changes. For OFF-VM durability, sync the backup dir to a private remote (see the note below).
#
# It excludes the same throwaway/local/secret bits the inner .claude/.gitignore excludes: hook logs,
# local settings, worktrees, the scheduler lock, and the MCP memory store.

set -euo pipefail

# 1. Resolve paths (repo root = this script's parent's parent).
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
CLAUDE_DIR="${REPO_ROOT}/.claude"
BACKUP_DIR="${DOCFORGE_CLAUDE_BACKUP_DIR:-/home/dev-center/backups}"
RETENTION="${DOCFORGE_CLAUDE_BACKUP_RETENTION:-14}"

if [[ ! -d "${CLAUDE_DIR}" ]]; then
  echo "no .claude/ at ${CLAUDE_DIR} — nothing to back up" >&2
  exit 1
fi
mkdir -p "${BACKUP_DIR}"

# 2. Timestamped tarball; exclude the local/secret/large paths (mirrors .claude/.gitignore).
STAMP="$(date +%Y-%m-%dT%H%M%S)"
ARCHIVE="${BACKUP_DIR}/docforge-claude-${STAMP}.tar.gz"
tar -czf "${ARCHIVE}" -C "${REPO_ROOT}" \
  --exclude='.claude/hooks/logs' \
  --exclude='.claude/worktrees' \
  --exclude='.claude/settings.local.json' \
  --exclude='.claude/hooks/hooks-config.local.json' \
  --exclude='.claude/mcp-memory.json' \
  --exclude='.claude/scheduled_tasks.lock' \
  --exclude='**/__pycache__' \
  .claude
echo "backed up .claude/ -> ${ARCHIVE} ($(du -h "${ARCHIVE}" | cut -f1))"

# 3. Retention: keep the newest ${RETENTION} snapshots, prune older ones.
mapfile -t OLD < <(ls -1t "${BACKUP_DIR}"/docforge-claude-*.tar.gz 2>/dev/null | tail -n +"$((RETENTION + 1))")
if [[ ${#OLD[@]} -gt 0 ]]; then
  printf '%s\n' "${OLD[@]}" | xargs -r rm -f
  echo "pruned ${#OLD[@]} old snapshot(s) beyond retention=${RETENTION}"
fi

# NOTE — off-VM durability: this backup lives on the same VM as the source. For true loss protection,
# sync ${BACKUP_DIR} to a PRIVATE remote (a private git repo, object storage, or another host). The
# public DocForge repo must NOT hold .claude/ content.
