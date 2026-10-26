# Copy of the AI Dev Kit's core/aidk/drift.py, written by aidk project onboard/upgrade: change the kit, not this file.
"""Drift: what a branch does that the kit's method forbids, found by the harness from git alone (not by a model).

One copy of the rules for every place that checks a branch: aidk verify, aidk done and the pre-push hook on the
agents' machine, and the CI job aidk-checks (core/ci), which runs a copy of this file on the forge's runners.
Standard library only: the CI has git and Python 3.8+, nothing else.

  out_of_scope     a file outside the owns: globs of the task (aidk ticket, the request's description)
  asserts_removed  a test file left with fewer assertions than it had
  test_disabled    a test file gains a skip, an xfail or a .only
  test_deleted     a test file deleted
  sensitive        never blocking: a project's own file changed (AGENTS.md, .aidk/, the CI, an agent tool's
                   settings...), right in the branch, listed for the user's review

A commit of the branch may lift a blocking rule with a line `aidk-allow: <rule>` in its message: explicit, and
visible in the request. Indicative, not proof: the CI and the review decide.
"""
import fnmatch
import os
import re

CODES = ("out_of_scope", "asserts_removed", "test_disabled", "test_deleted", "sensitive", "protected_path")
LABELS = {
    "en": {"protected_path": "protected file", "out_of_scope": "out of scope", "asserts_removed": "assertions removed",
           "test_disabled": "test disabled", "test_deleted": "test deleted", "sensitive": "sensitive file"},
    "fr": {"protected_path": "chemin protégé", "out_of_scope": "hors périmètre", "asserts_removed": "assertions retirées",
           "test_disabled": "test désactivé", "test_deleted": "test supprimé", "sensitive": "fichier sensible"},
}
WHY = {
    "en": {"protected_path": "a file nobody but the user changes",
           "sensitive": "the branch changes a project's own file (AGENTS.md, .aidk/, the CI...): look at it",
           "out_of_scope": "a file outside the owns: paths of the task",
           "asserts_removed": "a test file was left with fewer assertions than it had",
           "test_disabled": "a skip, an xfail or a .only was added to a test",
           "test_deleted": "a test file was deleted"},
    "fr": {"protected_path": "un fichier que seul l'utilisateur modifie",
           "sensitive": "la branche change un fichier propre au projet (AGENTS.md, .aidk/, la CI…) : à regarder",
           "out_of_scope": "un fichier hors des chemins owns: de la tâche",
           "asserts_removed": "un fichier de test a été laissé avec moins d'assertions qu'avant",
           "test_disabled": "un skip, un xfail ou un .only a été ajouté à un test",
           "test_deleted": "un fichier de test a été supprimé"},
}
TEST_FILE = re.compile(r"(^|/)(tests?/|__tests__/|test_[^/]*\.py$|[^/]*_test\.(py|go)$|[^/]*\.(test|spec)\.[cm]?[jt]sx?$)")
ASSERTS = re.compile(r"\bassert\b|\bexpect\(|\.should\b|\bassert[A-Z]\w*\(|\bself\.assert\w*\(")
SKIPS = re.compile(r"@pytest\.mark\.(skip|xfail)|pytest\.skip\(|@unittest\.skip|\b(it|test|describe)\.skip\(|"
                   r"\bx(it|test|describe)\(|\.only\(|t\.Skip\(")


def rel(path, top):
    """Path relative to the repository, with forward slashes (a leading "./" or "a/../" cannot hide a folder)."""
    path = os.path.normpath(str(path or "")).replace("\\", "/") if path else ""
    top = os.path.normpath(top).replace("\\", "/").rstrip("/") if top else ""
    if top and (path.lower() + "/").startswith(top.lower() + "/"):
        path = path[len(top) + 1:]
    return path[2:] if path.startswith("./") else path


def parse_owns(brief):
    """The owns: globs written in a text (a task's brief, a request's description)."""
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


# A project's own files, as globs: changed in a branch, they flag it for the user's review (aidk done labels the
# request, aidk merge never merges it alone). The CI job reads this list from its copy of this file.
SENSITIVE_GLOBS = (".aidk/*", ".gitlab/*", ".github/*", "AGENTS.md", "CLAUDE.md", "*/AGENTS.md", "*/CLAUDE.md",
                   ".mcp.json", ".claude/*", ".codex/*", ".cursor/*", ".agents/*", ".opencode/*",
                   ".pre-commit-config.yaml", "orca.yaml", ".worktreeinclude", ".gitlab-ci.yml", ".secrets.baseline")
# Files nobody but the user changes: none in the kit's v3 (an agent changes a project's own files in its branch,
# flagged as sensitive). Kept for the rules' shape and a project's own list.
PROTECTED_GLOBS = ()


def protected_globs():
    return list(PROTECTED_GLOBS)


def sensitive_globs():
    return list(SENSITIVE_GLOBS)


def is_protected(path, globs):
    return any(fnmatch.fnmatch(path, g) or path == g.rstrip("/*") for g in globs)


def check_edits(files, edits, scope, protected, deleted=()):
    """The drifts of a change to FILES (paths relative to the repository; EDITS: [(old text, new text)])."""
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


# --- the rules on a whole branch: aidk verify, aidk done, the pre-push hook and the CI job (aidk_checks.py) -------
BLOCKING = ("asserts_removed", "test_disabled", "test_deleted", "out_of_scope")
ALLOW_LINE = re.compile(r"^aidk-allow:\s*([a-z_ ,]+)$", re.M)


def _git(root, *args):
    import subprocess
    try:
        out = subprocess.run(["git", "-c", "core.fsmonitor=false", "-c", "core.quotepath=false", "-C", root] + list(args),
                             capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=60, check=False)
    except (OSError, subprocess.SubprocessError) as e:
        return 127, "%s: %s" % (type(e).__name__, e)
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
    """(ref, merge-base sha) of the branch against BASE, else origin/main, main, origin/master, master. A bare
    branch name (base = "main" in .aidk/project.toml) is read on the remote first: the local branch of a main
    checkout lags behind until something moves it (the kit's own clone moves only with aidk update), and a branch
    rebased on the remote would then seem to change every file merged since (P58)."""
    bases = (["origin/" + base] if base and "/" not in base else []) + ([base] if base else [])
    for ref in bases + ["origin/main", "main", "origin/master", "master"]:
        rc, mb = _git(root, "merge-base", ref, "HEAD")
        if rc == 0 and mb.strip():
            return ref, mb.strip()
    return None, None


def branch_rules(root, base_sha, owns=(), protected=(), sensitive=(), head="HEAD"):
    """(blocking, to_look, allowed): the drifts of the commits base_sha..HEAD, as [(code, detail)].
    Every changed file is checked like an edit: old content at base_sha, new content at HEAD; a changed file
    that SENSITIVE's globs match is to look at ("sensitive")."""
    rc, out = _git(root, "diff", "--name-status", "--no-renames", base_sha, head)
    if rc != 0:
        return [("git", "git diff %s..%s failed" % (base_sha[:12], head))], [], set()
    changes = []
    for line in out.splitlines():
        parts = line.split("\t")
        if len(parts) >= 2:
            changes.append((parts[0][:1], parts[-1]))
    # Only a test file's content matters (assertions, skips); for the others their path is enough.
    specs = [spec for status, path in changes if TEST_FILE.search(path)
             for spec in (["%s:%s" % (base_sha, path)] if status != "A" else []) +
             (["%s:%s" % (head, path)] if status != "D" else [])]
    blobs = _blobs(root, specs)
    found = []
    for status, path in changes:
        old = blobs.get("%s:%s" % (base_sha, path), "")
        new = blobs.get("%s:%s" % (head, path), "")
        found += check_edits([path], [(old, new)], list(owns), list(protected), {path} if status == "D" else set())
        if sensitive and is_protected(path, sensitive) and not is_protected(path, protected):
            found.append(("sensitive", path))
    _, messages = _git(root, "log", "--format=%B", "%s..%s" % (base_sha, head))
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
