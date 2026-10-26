#!/usr/bin/env python3
"""aidk-checks: the kit's drift rules replayed by the forge's CI on a merge request, whatever wrote the branch.

The same rules as aidk verify, aidk done and the pre-push hook on the agents' machine (drift.py, a copy of the
kit's core/aidk/drift.py written next to this file by aidk onboard and aidk upgrade), here on runners nobody's
agent controls. With "Pipelines must succeed" (GitLab) or a required status check (GitHub), a branch that weakens
a test or leaves its ticket's scope cannot be merged; aidk merge requires a green CI too.

  blocking   assertions removed from a test, a test disabled (skip, xfail, .only) or deleted, a file
             outside the owns: globs of the merge request's description
  to look at the project's own files changed (sensitive: AGENTS.md, .aidk/, orca.yaml, the CI, an agent tool's
             settings...): right in the branch, listed for the reviewer

A commit of the branch may lift a blocking rule with a line `aidk-allow: <rule>` in its message:
explicit, and visible in the merge request.

Base and scope come from the CI: GitLab's merge request variables (CI_MERGE_REQUEST_DIFF_BASE_SHA,
CI_MERGE_REQUEST_DESCRIPTION), GitHub's pull_request event (GITHUB_EVENT_PATH). On GitHub the branch judged is
the pull request's own head (pull_request.head.sha, else the second parent of the refs/pull/N/merge checkout)
against its merge-base with origin/<GITHUB_BASE_REF> today: the event's base.sha is the base when the pull
request was last synced, and the base's later commits are not the branch's. Outside a merge request
there is nothing to compare: the job passes. Options: --base REF, --owns GLOB,GLOB (tests, other forges).
Needs git and Python 3.8+, nothing else. Exit 0: mergeable for the kit's rules; 1: a blocking drift; 2: usage.
"""
import json
import os
import sys

sys.dont_write_bytecode = True  # nothing left in the repository's .aidk/ci
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import drift  # noqa: E402  (the copy next to this file)

PROTECTED = list(getattr(drift, "PROTECTED_GLOBS", ()))
SENSITIVE = list(getattr(drift, "SENSITIVE_GLOBS", ()))  # the list of the drift.py copied next to this file


def _arg(argv, name):
    for i, a in enumerate(argv):
        if a == name and i + 1 < len(argv):
            return argv[i + 1]
        if a.startswith(name + "="):
            return a.split("=", 1)[1]
    return None


def from_ci(env):
    """([base candidates], merge request description, [head candidates]) of this pipeline, or ([], "", ["HEAD"])
    outside a merge request; the first candidate that names a commit here wins (_commit)."""
    if env.get("CI_MERGE_REQUEST_DIFF_BASE_SHA"):  # GitLab, merge request pipeline
        return [env["CI_MERGE_REQUEST_DIFF_BASE_SHA"]], env.get("CI_MERGE_REQUEST_DESCRIPTION", ""), ["HEAD"]
    if env.get("GITHUB_EVENT_PATH") and env.get("GITHUB_BASE_REF"):  # GitHub, pull_request event
        # HEAD is refs/pull/N/merge: the pull request merged into the base of the checkout, its parents the base
        # and the pull request's head.
        merge_ref = env.get("GITHUB_REF", "").startswith("refs/pull/") and env["GITHUB_REF"].endswith("/merge")
        heads = ["HEAD^2"] if merge_ref else []
        try:
            with open(env["GITHUB_EVENT_PATH"], encoding="utf-8") as f:
                event = json.load(f)
            pr = event.get("pull_request") or {}
            base_sha, head_sha = (pr.get("base") or {}).get("sha"), (pr.get("head") or {}).get("sha")
            return (["origin/" + env["GITHUB_BASE_REF"]] + ([base_sha] if base_sha else []), pr.get("body") or "",
                    ([head_sha] if head_sha else []) + heads + ["HEAD"])
        except (OSError, ValueError, AttributeError):
            return ["origin/" + env["GITHUB_BASE_REF"]], "", heads + ["HEAD"]
    return [], "", ["HEAD"]


def _commit(root, refs):
    """The first of refs that names a commit of this clone, as a sha, or None."""
    for ref in refs:
        rc, out = drift._git(root, "rev-parse", "--verify", "--quiet", ref + "^{commit}")
        if rc == 0 and out.strip():
            return out.strip()
    return None


def main(argv=None, env=None):
    argv = sys.argv[1:] if argv is None else argv
    env = os.environ if env is None else env
    if any(a in ("-h", "--help") for a in argv):
        print(__doc__.strip())
        return 0
    root = os.getcwd()
    bases, description, heads = from_ci(env)
    bases = [_arg(argv, "--base")] if _arg(argv, "--base") else bases
    owns_arg = _arg(argv, "--owns")
    owns = [g.strip() for g in owns_arg.split(",") if g.strip()] if owns_arg is not None else drift.parse_owns(description)
    if not bases:
        print("aidk-checks: not a merge request pipeline: nothing to compare, passed")
        return 0
    base, head = _commit(root, bases) or bases[0], _commit(root, heads) or "HEAD"
    rc, mb = drift._git(root, "merge-base", base, head)
    if rc != 0 or not mb.strip():
        print("aidk-checks: no common history with %s: fetch more of it (GIT_DEPTH: 0, fetch-depth: 0)" % base)
        return 1
    blocking, to_look, allowed = drift.branch_rules(root, mb.strip(), owns, PROTECTED, SENSITIVE, head=head)
    labels = drift.LABELS["en"]
    print("aidk-checks: branch %s against %s%s"
          % (head[:12], base[:12], (" · owns: " + ", ".join(owns)) if owns else ""))
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
