#!/usr/bin/env python3
"""aidk-checks: the kit's drift rules replayed by the forge's CI on a merge request, whatever wrote the branch.

The same rules as aidk verify and aidk done on the agents' machine (drift.py, a copy of the kit's
core/harness/aidk_harness/drift.py written next to this file by aidk onboard and aidk upgrade), here on
runners nobody's agent controls. With "Pipelines must succeed" (GitLab) or a required status check
(GitHub), a branch that weakens a test or leaves its ticket's scope cannot be merged.

  blocking   assertions removed from a test, a test disabled (skip, xfail, .only) or deleted, a file
             outside the owns: globs of the merge request's description
  to look at a protected file changed (.claude/, .aidk/, AGENTS.md, the CI...): right in the user's own
             onboarding merge request, to look at in an agent's

A commit of the branch may lift a blocking rule with a line `aidk-allow: <rule>` in its message:
explicit, and visible in the merge request.

Base and scope come from the CI: GitLab's merge request variables (CI_MERGE_REQUEST_DIFF_BASE_SHA,
CI_MERGE_REQUEST_DESCRIPTION), GitHub's pull_request event (GITHUB_EVENT_PATH). Outside a merge request
there is nothing to compare: the job passes. Options: --base REF, --owns GLOB,GLOB (tests, other forges).
Needs git and Python 3.8+, nothing else. Exit 0: mergeable for the kit's rules; 1: a blocking drift; 2: usage.
"""
import json
import os
import sys

sys.dont_write_bytecode = True  # nothing left in the repository's .aidk/ci
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import drift  # noqa: E402  (the copy next to this file)

PROTECTED = [".claude/*", ".aidk/*", ".gitlab/*", ".github/*", "AGENTS.md", "CLAUDE.md", ".mcp.json",
             ".pre-commit-config.yaml", "orca.yaml", ".worktreeinclude", ".gitlab-ci.yml",
             "*/AGENTS.md", "*/CLAUDE.md"]


def _arg(argv, name):
    for i, a in enumerate(argv):
        if a == name and i + 1 < len(argv):
            return argv[i + 1]
        if a.startswith(name + "="):
            return a.split("=", 1)[1]
    return None


def from_ci(env):
    """(base ref or sha, merge request description) of this pipeline, or (None, "") outside a merge request."""
    if env.get("CI_MERGE_REQUEST_DIFF_BASE_SHA"):  # GitLab, merge request pipeline
        return env["CI_MERGE_REQUEST_DIFF_BASE_SHA"], env.get("CI_MERGE_REQUEST_DESCRIPTION", "")
    if env.get("GITHUB_EVENT_PATH") and env.get("GITHUB_BASE_REF"):  # GitHub, pull_request event
        try:
            with open(env["GITHUB_EVENT_PATH"], encoding="utf-8") as f:
                event = json.load(f)
            pr = event.get("pull_request") or {}
            return (pr.get("base") or {}).get("sha") or "origin/" + env["GITHUB_BASE_REF"], pr.get("body") or ""
        except (OSError, ValueError, AttributeError):
            return "origin/" + env["GITHUB_BASE_REF"], ""
    return None, ""


def main(argv=None, env=None):
    argv = sys.argv[1:] if argv is None else argv
    env = os.environ if env is None else env
    if any(a in ("-h", "--help") for a in argv):
        print(__doc__.strip())
        return 0
    root = os.getcwd()
    base, description = from_ci(env)
    base = _arg(argv, "--base") or base
    owns_arg = _arg(argv, "--owns")
    owns = [g.strip() for g in owns_arg.split(",") if g.strip()] if owns_arg is not None else drift.parse_owns(description)
    if not base:
        print("aidk-checks: not a merge request pipeline: nothing to compare, passed")
        return 0
    rc, mb = drift._git(root, "merge-base", base, "HEAD")
    if rc != 0 or not mb.strip():
        print("aidk-checks: no common history with %s: fetch more of it (GIT_DEPTH: 0, fetch-depth: 0)" % base)
        return 1
    blocking, to_look, allowed = drift.branch_rules(root, mb.strip(), owns, PROTECTED)
    labels = drift.LABELS["en"]
    print("aidk-checks: branch against %s%s" % (base[:40], (" · owns: " + ", ".join(owns)) if owns else ""))
    if allowed:
        print("  allowed by a commit (aidk-allow): %s" % ", ".join(sorted(allowed)))
    for code, detail in to_look[:30]:
        print("  to look at · %s: %s" % (labels.get(code, code), detail))
    for code, detail in blocking[:50]:
        print("  BLOCKING   · %s: %s" % (labels.get(code, code), detail))
    if blocking:
        print("aidk-checks: FAILED: %d blocking drift(s). Fix them, or lift one on purpose with a commit line "
              "`aidk-allow: <rule>` (%s)." % (len(blocking), ", ".join(drift.BLOCKING)))
        return 1
    print("aidk-checks: OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
