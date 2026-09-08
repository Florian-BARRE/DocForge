# ====== Code Summary ======
# ParseSubprocessError — the single typed failure the in-worker Docling parse raises when its
# isolated subprocess hit a CAP (memory / time) or DIED (crash / OOM-kill). It is what the engine's
# breadcrumb reports as the failing node's error_type, so a job that blew the parse budget fails
# CLEANLY and ATTRIBUTED ("this document is too heavy for docling at this budget") instead of wedging
# the worker forever on a thread that can never be killed. A genuine docling CONVERT error (a corrupt
# PDF) is NOT this type — the pool re-raises that as a plain RuntimeError so its chained cause still
# names the real failure. This one means the isolation mechanism fired.


class ParseSubprocessError(RuntimeError):
    """The in-worker parse exceeded its memory/time budget or its isolated subprocess died.

    Raised by the parent (the worker) — never inside a node's own convert — so the failure is a
    normal, attributed FAILED job: the worker survives, the parse subprocess is killed/reaped, and no
    process-wide lock is left held. Subclasses RuntimeError so any caller that already handles a
    parse RuntimeError keeps working.
    """


__all__ = ["ParseSubprocessError"]
