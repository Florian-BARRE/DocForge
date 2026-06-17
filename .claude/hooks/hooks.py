#!/usr/bin/env python3
"""
DocForge Claude Code hooks — structured event logging.

Invoked by Claude Code for every configured hook event. Reads the JSON
payload from stdin, checks per-event config, then appends a structured
entry to .claude/hooks/logs/hooks-log.jsonl.

Design constraint: always exits 0. A non-zero exit would block Claude.

Usage (set in settings.json):
  python3 .claude/hooks/hooks.py <EventName>
"""

# ====== Standard Library Imports ======
import datetime
import json
import os
import sys
from pathlib import Path


# ─── Paths ───
_HERE = Path(__file__).parent
LOG_DIR = _HERE / "logs"
LOG_FILE = LOG_DIR / "hooks-log.jsonl"
CONFIG_FILE = _HERE / "hooks-config.json"
LOCAL_CONFIG_FILE = _HERE / "hooks-config.local.json"

# Maximum log file size before rotation (5 MB).
MAX_LOG_BYTES = 5 * 1024 * 1024


def _load_config() -> dict:
    """
    Load hook config from hooks-config.json, then overlay hooks-config.local.json.

    Local file values always win — lets individual developers disable noisy
    hooks without touching the shared config.

    Returns:
        dict: Merged configuration dictionary.
    """
    config: dict = {}
    for path in [CONFIG_FILE, LOCAL_CONFIG_FILE]:
        if path.exists():
            try:
                with open(path, encoding="utf-8") as fh:
                    config.update(json.load(fh))
            except (json.JSONDecodeError, OSError):
                pass
    return config


def _is_hook_disabled(event_name: str, config: dict) -> bool:
    """
    Return True if this specific hook event is disabled in config.

    Args:
        event_name (str): Hook event name (e.g. "PreToolUse").
        config (dict): Merged config dict.

    Returns:
        bool: True if the hook should be skipped.
    """
    key = f"disable{event_name}"
    return bool(config.get(key, False))


def _is_logging_disabled(config: dict) -> bool:
    """
    Return True if logging is globally disabled.

    Args:
        config (dict): Merged config dict.

    Returns:
        bool: True if logging should be skipped.
    """
    return bool(config.get("disableLogging", False))


def _rotate_if_needed() -> None:
    """
    Rotate the log file by renaming it with a timestamp suffix when it
    exceeds MAX_LOG_BYTES. Only one rotated copy is kept to avoid filling disk.
    """
    if LOG_FILE.exists() and LOG_FILE.stat().st_size > MAX_LOG_BYTES:
        stamp = datetime.datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
        LOG_FILE.rename(LOG_FILE.with_suffix(f".{stamp}.jsonl"))


def _log_event(event_name: str, payload: dict) -> None:
    """
    Append a single structured JSON line to hooks-log.jsonl.

    Args:
        event_name (str): Hook event name.
        payload (dict): Raw JSON payload received on stdin.
    """
    # 1. Ensure log directory exists
    LOG_DIR.mkdir(parents=True, exist_ok=True)

    # 2. Rotate if the file is too large
    _rotate_if_needed()

    # 3. Build the log entry
    entry = {
        "ts": datetime.datetime.utcnow().isoformat() + "Z",
        "event": event_name,
        "pid": os.getpid(),
        "payload": payload,
    }

    # 4. Append to JSONL file
    with open(LOG_FILE, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry, ensure_ascii=False) + "\n")


def main() -> None:
    """
    Entry point — read event name from argv, payload from stdin, log if enabled.

    Always exits 0 to avoid blocking Claude Code.
    """
    # 1. Determine event name from CLI arg
    event_name = sys.argv[1] if len(sys.argv) > 1 else "Unknown"

    # 2. Load per-hook enable/disable config
    config = _load_config()

    # 3. Parse JSON payload from stdin (gracefully handle empty/malformed input)
    try:
        raw = sys.stdin.read()
        payload = json.loads(raw) if raw.strip() else {}
    except Exception:
        payload = {}

    # 4. Skip if this hook is disabled
    if _is_hook_disabled(event_name, config):
        sys.exit(0)

    # 5. Append structured log entry
    if not _is_logging_disabled(config):
        try:
            _log_event(event_name, payload)
        except Exception:
            # Never let a logging error block Claude
            pass

    sys.exit(0)


if __name__ == "__main__":
    main()
