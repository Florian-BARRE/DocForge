# Copy of the AI Dev Kit's core/harness/aidk_harness/drift.py, written by aidk onboard and aidk upgrade: change the kit, not this file.
"""Drift: what an agent does that its method forbids, noticed by the harness (not by the model).

One copy of the rules for every edition: the VM's trace hook (hooks/aidk-trace, from /opt/aidk/lib)
and aidk_harness.live (the workstation) call the checks below on each hook event; the rules that need
the session's history (same_failure, no_test) are counted by each of them with the helpers here.

  protected_path   a file the agents must not edit (.claude/, AGENTS.md, CI files...; the guard refuses
                   the edit, the attempt is still a drift)
  out_of_scope     a subagent edits outside the `owns:` globs of its brief
  asserts_removed  an edit of a test file leaves fewer assertions than it found
  test_disabled    an edit of a test file adds a skip / xfail / .only
  test_deleted     a shell command removes test files
  lead_writes      the lead writes files itself through the shell instead of delegating
  same_failure     the same failing tests three times in one request
  no_test          an implementer or test-writer edited code and returned without running a test

Each drift is (code, detail): the detail names the file, the command or the tests, for the status line's
list. Indicative, not proof: the end-of-task check and the forge's CI remain what decides.
"""
import fnmatch
import os
import re

CODES = ("protected_path", "out_of_scope", "asserts_removed", "test_disabled", "test_deleted", "lead_writes",
         "same_failure", "no_test")
# What a drift is called, and what its rule means, in the two languages of the kit's installs. The VM's
# traces (Loki, its dashboards) use the French names as they are.
LABELS = {
    "en": {"protected_path": "protected file", "out_of_scope": "out of scope", "asserts_removed": "assertions removed",
           "test_disabled": "test disabled", "test_deleted": "test deleted", "lead_writes": "lead writes itself",
           "same_failure": "same failure ×3", "no_test": "no test run"},
    "fr": {"protected_path": "chemin protégé", "out_of_scope": "hors périmètre", "asserts_removed": "assertions retirées",
           "test_disabled": "test désactivé", "test_deleted": "test supprimé", "lead_writes": "lead écrit lui-même",
           "same_failure": "même échec ×3", "no_test": "aucun test lancé"},
}
WHY = {
    "en": {"protected_path": "an agent tried to change a file only you change (.claude/, AGENTS.md, CI...)",
           "out_of_scope": "a subagent edited a file outside the owns: paths of its brief",
           "asserts_removed": "an edit of a test file left fewer assertions than it found",
           "test_disabled": "an edit added a skip, an xfail or a .only to a test",
           "test_deleted": "a command deleted test files",
           "lead_writes": "the lead wrote files through the shell instead of delegating",
           "same_failure": "the same tests failed three times in this request",
           "no_test": "a subagent edited code and returned without running a test"},
    "fr": {"protected_path": "un agent a voulu modifier un fichier que toi seul modifies (.claude/, AGENTS.md, CI…)",
           "out_of_scope": "un sous-agent a modifié un fichier hors des chemins owns: de sa consigne",
           "asserts_removed": "une modification d'un fichier de test a laissé moins d'assertions qu'avant",
           "test_disabled": "une modification a ajouté un skip, un xfail ou un .only à un test",
           "test_deleted": "une commande a effacé des fichiers de test",
           "lead_writes": "le lead a écrit des fichiers par le shell au lieu de déléguer",
           "same_failure": "les mêmes tests ont échoué trois fois dans cette demande",
           "no_test": "un sous-agent a modifié du code et rendu la main sans lancer de test"},
}
SHELL_TOOLS = ("Bash", "PowerShell", "shell", "local_shell", "exec_command", "container.exec")  # Claude Code, Codex
EDIT_TOOLS = ("Edit", "MultiEdit", "Write", "NotebookEdit", "apply_patch")
TEST_FILE = re.compile(r"(^|/)(tests?/|__tests__/|test_[^/]*\.py$|[^/]*_test\.(py|go)$|[^/]*\.(test|spec)\.[cm]?[jt]sx?$)")
TEST_RUNNERS = re.compile(r"^(pytest|py\.test|vitest|jest|tox|nox|go test|cargo test|make test|"
                          r"(npm|pnpm|yarn|bun)( run)? test|python3? -m (pytest|unittest)|python(\.exe)? -m (pytest|unittest))\b")
RUN_PREFIX = re.compile(r"^((\w+=\S*\s+)|(uv|poetry|pdm|hatch|pipenv|rye) run\s+(--\S+\s+(\S+\s+)?)*|npx\s+|bunx\s+|"
                        r"pnpm exec\s+|timeout\s+\S+\s+|nice\s+|time\s+|env\s+)+")
TEST_FAILED = re.compile(r"\b[1-9]\d* (failed|failing|errors?)\b|test result: FAILED|^FAIL\b|^FAILED\b|"
                         r"Tests:\s+\d+ failed", re.M)
ASSERTS = re.compile(r"\bassert\b|\bexpect\(|\.should\b|\bassert[A-Z]\w*\(|\bself\.assert\w*\(")
QUOTED = re.compile(r"'[^']*'|\"(?:[^\"\\]|\\.)*\"")
SKIPS = re.compile(r"@pytest\.mark\.(skip|xfail)|pytest\.skip\(|@unittest\.skip|\b(it|test|describe)\.skip\(|"
                   r"\bx(it|test|describe)\(|\.only\(|t\.Skip\(")
LEAD_WRITES = re.compile(r"(\bsed\s+(-\w*\s+)*-i|\bperl\s+-p?i|\btee\s+(-a\s+)?(?!/dev/)[\w./-]|\bcat\s*>|"
                         r"(?<![0-9&=<>-])>>?\s*(?!/dev/(null|stderr|stdout)\b|\$null\b|NUL(?=\s|$|[;&|)]))[\w./\\-]|"
                         r"\bgit\s+apply\b|\bpatch\s|\btruncate\s|\bdd\s+of=|"
                         r"\b(Set-Content|Add-Content|Out-File)\b|\bNew-Item\b[^;|]*-ItemType\s+File)", re.I)
RM_TESTS = re.compile(r"\b(rm|git\s+rm|del|Remove-Item)\b[^;&|]*\btests?\b|"
                      r"\b(rm|git\s+rm|del|Remove-Item)\b[^;&|]*(test_\w+\.py|\.(test|spec)\.[jt]sx?)", re.I)
IMPLEMENTERS = ("implementer", "test-writer")


def rel(path, top):
    """Path relative to the repository, with forward slashes (a leading "./" or "a/../" cannot hide .claude/)."""
    path = os.path.normpath(str(path or "")).replace("\\", "/") if path else ""
    top = os.path.normpath(top).replace("\\", "/").rstrip("/") if top else ""
    if top and (path.lower() + "/").startswith(top.lower() + "/"):
        path = path[len(top) + 1:]
    return path[2:] if path.startswith("./") else path


def edits_of(name, ti):
    """(files, [(old, new)], deleted files) of an edit tool call, Claude Code's or Codex's apply_patch."""
    ti = ti if isinstance(ti, dict) else {}
    if name == "apply_patch":
        patch = str(ti.get("patch") or ti.get("input") or "")
        files = re.findall(r"^\*\*\* (?:Add|Update|Delete) File: (.+)$", patch, re.M)
        deleted = re.findall(r"^\*\*\* Delete File: (.+)$", patch, re.M)
        old = "\n".join(line[1:] for line in patch.splitlines() if line.startswith("-") and not line.startswith("---"))
        new = "\n".join(line[1:] for line in patch.splitlines() if line.startswith("+") and not line.startswith("+++"))
        return files, [(old, new)], deleted
    path = ti.get("file_path") or ti.get("notebook_path") or ""
    if name == "MultiEdit":
        edits = [(e.get("old_string", ""), e.get("new_string", "")) for e in ti.get("edits", []) if isinstance(e, dict)]
    elif name == "Write":
        edits = [("", ti.get("content", ""))]
    elif name == "NotebookEdit":
        edits = [("", ti.get("new_source", ""))]
    else:
        edits = [(ti.get("old_string", ""), ti.get("new_string", ""))]
    return ([path] if isinstance(path, str) and path else []), [(str(o or ""), str(n or "")) for o, n in edits], []


def is_test_cmd(cmd):
    for seg in re.split(r"&&|\|\||[;|&\n]", QUOTED.sub("''", cmd or "")):
        seg = RUN_PREFIX.sub("", seg.strip())
        if TEST_RUNNERS.match(seg):
            return True
    return False


def parse_owns(brief):
    globs = []
    for line in (brief or "").splitlines():
        m = re.match(r"\s*[-*]?\s*owns\s*:\s*(.+)$", line, re.I)
        if m:
            globs += [g.strip().strip("`") for g in re.split(r"[,\s]+", m.group(1)) if g.strip()]
    return globs[:40]


def matches(path, globs):
    for g in globs:
        g2 = g.rstrip("/")
        if fnmatch.fnmatch(path, g) or fnmatch.fnmatch(path, g2 + "/*") or path == g2 or path.startswith(g2 + "/"):
            return True
    return False


def failed_tests(text):
    names = re.findall(r"^FAILED ([^\s]+)", text, re.M)                     # pytest
    names += re.findall(r"^\s*(?:FAIL|×|✗)\s+(\S+.*?)(?:\s+\d+ms)?$", text, re.M)  # vitest / jest
    names += re.findall(r"^--- FAIL: (\S+)", text, re.M)                      # go
    out = []
    for n in names:
        n = n.strip()
        if n and n not in out:
            out.append(n)
    return out[:30]


def protected_globs():
    """The files the agents must not edit, as globs, from the guard's list (this install's forge)."""
    from . import guard
    dirs, files = guard.protected()
    return [d + "/*" for d in dirs] + list(files) + ["*/AGENTS.md", "*/CLAUDE.md"]


def is_protected(path, globs):
    return any(fnmatch.fnmatch(path, g) or path == g.rstrip("/*") for g in globs)


def check_edits(files, edits, scope, protected, deleted=()):
    """The drifts of an edit (paths relative to the repository): [(code, detail)]."""
    out = []
    old = "".join(o for o, _ in edits)
    new = "".join(n for _, n in edits)
    for r in files:
        if is_protected(r, protected):
            out.append(("protected_path", r))
        elif scope and not matches(r, scope):
            out.append(("out_of_scope", "%s (owns: %s)" % (r, ", ".join(scope))))
        if TEST_FILE.search(r):
            if old and len(ASSERTS.findall(new)) < len(ASSERTS.findall(old)):
                out.append(("asserts_removed", "%s: %d → %d" % (r, len(ASSERTS.findall(old)), len(ASSERTS.findall(new)))))
            if len(SKIPS.findall(new)) > len(SKIPS.findall(old)):
                out.append(("test_disabled", r))
            if r in deleted:
                out.append(("test_deleted", r))
    return out


def check_shell(cmd, is_lead):
    """The drifts of a shell command: [(code, detail)]."""
    out = []
    if RM_TESTS.search(cmd or ""):
        out.append(("test_deleted", cmd))
    if is_lead and LEAD_WRITES.search(QUOTED.sub("''", cmd or "")):
        out.append(("lead_writes", cmd))
    return out


def before_tool(name, ti, top, is_lead, scope, protected=None):
    """The drifts of a tool call about to run (the workstation's view of a hook event): [(code, detail)]."""
    ti = ti if isinstance(ti, dict) else {}
    if name in EDIT_TOOLS:
        files, edits, deleted = edits_of(name, ti)
        return check_edits([rel(f, top) for f in files], edits, scope,
                           protected if protected is not None else protected_globs(), {rel(f, top) for f in deleted})
    if name in SHELL_TOOLS:
        cmd = ti.get("command")
        if isinstance(cmd, list):  # Codex wraps commands: ["bash", "-lc", "uv run pytest"]
            cmd = cmd[2] if len(cmd) == 3 and cmd[1] in ("-c", "-lc") else " ".join(str(c) for c in cmd)
        return check_shell(cmd if isinstance(cmd, str) else "", is_lead)
    return []


# --- the same rules on a whole branch: aidk verify, aidk done and the CI job (aidk_checks.py) ---------------
# Drifts that block a branch (a test weakened, a file outside the ticket's owns:) and those that only ask for a
# look (a protected file changed: right in the user's own onboarding MR, wrong in an agent's). A commit of the
# branch may lift a blocking rule with a line `aidk-allow: <code>` in its message: explicit, and in the MR.
BLOCKING = ("asserts_removed", "test_disabled", "test_deleted", "out_of_scope")
ALLOW_LINE = re.compile(r"^aidk-allow:\s*([a-z_ ,]+)$", re.M)


def _git(root, *args):
    import subprocess
    out = subprocess.run(["git", "-c", "core.fsmonitor=false", "-c", "core.quotepath=false", "-C", root] + list(args),
                         capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=60, check=False)
    return out.returncode, out.stdout


def _blobs(root, specs):
    """{"<rev>:<path>": text} for every spec, read in one `git cat-file --batch` (one process, not one per
    file: on Windows each git call costs); a missing object is left out."""
    import subprocess
    if not specs:
        return {}
    try:
        out = subprocess.run(["git", "-c", "core.fsmonitor=false", "-C", root, "cat-file", "--batch"],
                             input=("\n".join(specs) + "\n").encode("utf-8"), capture_output=True, timeout=300,
                             check=False).stdout
    except (OSError, subprocess.SubprocessError):
        return {}
    found, pos = {}, 0
    for spec in specs:
        nl = out.find(b"\n", pos)
        if nl < 0:
            break
        header = out[pos:nl].split()
        pos = nl + 1
        if len(header) == 3 and header[1] == b"blob" and header[2].isdigit():
            size = int(header[2])
            found[spec] = out[pos:pos + size].decode("utf-8", "replace")
            pos += size + 1
    return found


def branch_base(root, base=""):
    """(ref, merge-base sha) of the branch against BASE, else origin/main, main, origin/master, master."""
    for ref in ([base] if base else []) + ["origin/main", "main", "origin/master", "master"]:
        rc, mb = _git(root, "merge-base", ref, "HEAD")
        if rc == 0 and mb.strip():
            return ref, mb.strip()
    return None, None


def branch_rules(root, base_sha, owns=(), protected=()):
    """(blocking, to_look, allowed): the drifts of the commits base_sha..HEAD, as [(code, detail)].
    Every changed file is checked like an edit: old content at base_sha, new content at HEAD."""
    rc, out = _git(root, "diff", "--name-status", "--no-renames", base_sha, "HEAD")
    if rc != 0:
        return [("git", "git diff %s..HEAD failed" % base_sha[:12])], [], set()
    changes = []
    for line in out.splitlines():
        parts = line.split("\t")
        if len(parts) >= 2:
            changes.append((parts[0][:1], parts[-1]))
    # Only a test file's content matters (assertions, skips); for the others their path is enough.
    specs = [spec for status, path in changes if TEST_FILE.search(path)
             for spec in (["%s:%s" % (base_sha, path)] if status != "A" else []) +
             (["HEAD:%s" % path] if status != "D" else [])]
    blobs = _blobs(root, specs)
    found = []
    for status, path in changes:
        old = blobs.get("%s:%s" % (base_sha, path), "")
        new = blobs.get("HEAD:%s" % path, "")
        found += check_edits([path], [(old, new)], list(owns), list(protected), {path} if status == "D" else set())
    _, messages = _git(root, "log", "--format=%B", "%s..HEAD" % base_sha)
    allowed = {c.strip() for m in ALLOW_LINE.findall(messages) for c in re.split(r"[ ,]+", m) if c.strip()}
    blocking = [(c, d) for c, d in found if c in BLOCKING and c not in allowed]
    to_look = [(c, d) for c, d in found if c not in BLOCKING]
    return blocking, to_look, allowed


def ticket_path(root):
    """<git dir>/aidk-ticket.json: the ticket this worktree works on (never committed, one per worktree)."""
    rc, out = _git(root, "rev-parse", "--absolute-git-dir")
    return os.path.join(out.strip(), "aidk-ticket.json") if rc == 0 and out.strip() else ""


def ticket(root):
    """{"id": "#42", "owns": [globs]} of this worktree, or {}."""
    import json
    path = ticket_path(root)
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return {}
    if not isinstance(data, dict):
        return {}
    owns = [g for g in data.get("owns") or [] if isinstance(g, str) and g][:40]
    return {"id": str(data.get("id") or "")[:40], "owns": owns}
