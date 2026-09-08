# ====== Code Summary ======
# The CHILD side of the killable parse subprocess. `serve` is the warm loop the worker forks once and
# then feeds one parse request at a time over a pipe: it applies the memory cap, imports the node
# class, runs its (heavy, native) convert IN THIS process, and ships the mapped IR back as JSON. The
# point of running here — not in a worker thread — is that this process CAN be killed: an OOM or a
# native infinite loop dies with the child, and the worker (the parent) survives with its lock intact.
# A convert that raises is reported back as an ("err", type, message) tuple (the loop keeps serving);
# a convert that OOM-kills or hangs kills the whole child, which the parent detects as a broken pipe.

# ====== Standard Library Imports ======
import importlib
from multiprocessing.connection import Connection
from typing import Any

# The largest error message shipped back to the parent — a full docling traceback string is already
# in the child's own logs; the parent only needs the human-readable cause on the job row.
_MAX_ERROR_CHARS = 2000


def _truncate(text: str) -> str:
    """Bound an error message shipped over the pipe so a pathological cause can't bloat the response."""
    return text if len(text) <= _MAX_ERROR_CHARS else text[:_MAX_ERROR_CHARS] + "…"


def _apply_memory_cap(memory_mb: int) -> None:
    """Cap this child's address space (RLIMIT_AS) so a runaway parse dies CLEAN, before the cgroup.

    A positive cap makes an over-budget allocation fail with a Python ``MemoryError`` the serve loop
    reports as an attributed error — BEFORE the container's cgroup OOM-killer would reap a process
    (possibly the worker itself). 0 disables it: the time cap + kill-on-death still bound the run, and
    a forked child inherits the parent's virtual footprint, so a too-low cap can be un-settable — in
    that case the guard is skipped rather than crashing the child.

    Args:
        memory_mb (int): The address-space budget in MiB (0 disables the cap).
    """
    if memory_mb <= 0:
        return
    # 1. Local import — `resource` is POSIX-only; the whole worker runs on Linux, but keep it lazy.
    import resource

    limit_bytes = int(memory_mb) * 1024 * 1024
    try:
        # 2. Keep the hard limit at least as tight as the requested soft cap; never RAISE a hard limit
        #    (only the privileged may), so clamp to the inherited hard ceiling when one exists.
        _soft, hard = resource.getrlimit(resource.RLIMIT_AS)
        new_hard = limit_bytes if hard == resource.RLIM_INFINITY else min(limit_bytes, hard)
        resource.setrlimit(resource.RLIMIT_AS, (limit_bytes, new_hard))
    except (ValueError, OSError):
        # 3. The inherited baseline already exceeds the cap — cannot lower it here without killing the
        #    child outright; fall back to the time cap + kill-on-death (which still protect the worker).
        pass


def _bootstrap(memory_mb: int) -> None:
    """Prepare the freshly-forked child: drop inherited log sinks, then apply the memory cap."""
    # 1. This child was forked from the multithreaded async worker: an inherited loguru sink whose
    #    internal lock a parent thread held at the fork instant can deadlock the child the first time
    #    it logs. Drop every inherited sink so the child starts from a clean logging state.
    try:
        from loggerplusplus import loggerplusplus

        loggerplusplus.remove()
    except Exception:
        pass
    # 2. Hard memory ceiling for this child's whole lifetime (belt to the parent's time cap braces).
    _apply_memory_cap(memory_mb)


def _resolve_node_class(module: str, qualname: str) -> Any:
    """Import and return the parser node class addressed by (module, dotted qualname)."""
    obj: Any = importlib.import_module(module)
    for part in qualname.split("."):
        obj = getattr(obj, part)
    return obj


def run_parse(request: dict[str, Any]) -> str:
    """Run one parse in this child and return the mapped IR as a JSON string.

    Reconstructs the node from its class + serialised config (the config crosses the process boundary
    as a plain dict), then calls its pure ``_convert_to_ir`` — the same convert + IR mapping the node
    would have run in-thread, only here it runs in a process the parent can kill.

    Args:
        request (dict): ``module``/``qualname`` (the node class), ``config`` (its NodeConfig as a
            dict), ``content`` (the source/PDF bytes), ``suffix`` (the temp-file extension) and
            ``source_hash`` (the IR doc id).

    Returns:
        str: The produced ``DocumentIR`` serialised with ``model_dump_json`` (JSON-safe: the parse IR
            carries no figure crops yet — figure_render embeds those downstream).
    """
    # 1. Rebuild the node from its class + config dict (the node is pure — no clients needed).
    node_cls = _resolve_node_class(request["module"], request["qualname"])
    node = node_cls("parse", node_cls.Config(**request["config"]))

    # 2. Run the heavy convert + IR mapping in THIS process and hand the IR back as JSON.
    ir = node._convert_to_ir(request["content"], request["suffix"], request["source_hash"])
    return ir.model_dump_json()


def serve(conn: Connection, memory_mb: int) -> None:
    """The warm child loop: bootstrap once, then answer one parse request per message until closed.

    Runs one request at a time (the parent serialises), so the node's process-wide converter cache
    loads its models ONCE and amortises across every document this child handles. A convert that
    raises is reported back and the loop keeps serving; a convert that kills the child (OOM / native
    hang the parent SIGKILLs) simply ends the process, which the parent sees as a broken pipe.

    Args:
        conn (Connection): The child end of the duplex pipe to the parent.
        memory_mb (int): The address-space cap to apply to this child (0 disables it).
    """
    # 1. One-time preparation (log sinks + memory cap) before the first request.
    _bootstrap(memory_mb)

    # 2. Serve until the parent closes the pipe or sends the shutdown sentinel (None).
    while True:
        try:
            request = conn.recv()
        except (EOFError, KeyboardInterrupt):
            return
        if request is None:
            return
        # 3. Run the parse; ANY failure (incl. MemoryError from the cap) is reported, not fatal — the
        #    loop keeps the warm models for the next document. A crash/OOM-kill never reaches here.
        try:
            response: tuple[Any, ...] = ("ok", run_parse(request))
        except Exception as exc:
            response = ("err", type(exc).__name__, _truncate(str(exc)))
        try:
            conn.send(response)
        except (BrokenPipeError, OSError):
            return


__all__ = ["serve", "run_parse"]
