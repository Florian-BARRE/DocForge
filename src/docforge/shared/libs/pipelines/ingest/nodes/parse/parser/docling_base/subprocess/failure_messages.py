# ====== Code Summary ======
# ParseFailureMessages — the attributed, ACTIONABLE job-error text for each way the isolated parse can
# be stopped (time cap, resident-memory watchdog, RLIMIT_AS cap, child death). Each names the limit
# that fired and the levers that fix it, so a FAILED job tells the operator what to change without
# shell access to the worker.


class ParseFailureMessages:
    """Static builders of the parse-subprocess failure reasons surfaced on the job row."""

    # The levers shared by every "too heavy" reason.
    # (The `light` business preset does NOT lighten the parse itself — it drops enrich/contextualize/
    # metagen — so the parse lever is the docling node's own OCR/table switches.)
    _LIGHTER = "lighten the parse (docling do_ocr / do_table_structure off), or split the document"

    def __new__(cls, *args: object, **kwargs: object) -> None:
        raise TypeError("ParseFailureMessages is a static-only class and cannot be instantiated.")

    @classmethod
    def timeout(cls, timeout_seconds: float) -> str:
        """The parse ran past its wall-clock cap and was SIGKILLed."""
        return (
            f"parse exceeded its {timeout_seconds}s time limit in an isolated subprocess — this "
            f"document is too heavy for docling at this limit; raise parse_timeout_seconds, "
            f"{cls._LIGHTER}, or lower worker concurrency"
        )

    @classmethod
    def rss_exceeded(cls, rss_limit_mb: int, peak_rss_mb: int) -> str:
        """The parse tree's RESIDENT memory crossed the watchdog limit and was SIGKILLed."""
        return (
            f"parse_memory_exceeded: the docling parse used {peak_rss_mb} MiB resident memory, over "
            f"its {rss_limit_mb} MiB limit, and was killed before the container ran out of memory — "
            f"raise parse_rss_limit_mb on the collection (or WORKER_PARSE_RSS_LIMIT_MB for the "
            f"deployment) if the worker has the headroom, {cls._LIGHTER}"
        )

    @classmethod
    def address_space_exceeded(cls, memory_mb: int, child_message: str) -> str:
        """The opt-in RLIMIT_AS cap made an allocation fail inside the child."""
        return (
            f"parse_memory_exceeded: the docling parse hit its {memory_mb} MiB address-space cap "
            f"(parse_memory_mb / WORKER_PARSE_MEMORY_MB, virtual memory) — raise or unset that cap, "
            f"{cls._LIGHTER} (child: {child_message})"
        )

    @classmethod
    def crashed(cls, timeout_seconds: float, rss_limit_mb: int) -> str:
        """The child died on its own (a native crash or the kernel OOM-killer)."""
        rss_cap = f"{rss_limit_mb} MiB resident" if rss_limit_mb > 0 else "no resident-memory"
        return (
            f"the parse subprocess died (a crash or out-of-memory kill) under a {timeout_seconds}s / "
            f"{rss_cap} limit — this document is likely too heavy for docling; "
            f"lower parse_rss_limit_mb / WORKER_PARSE_RSS_LIMIT_MB so the watchdog stops it cleanly "
            f"first, {cls._LIGHTER}, or lower worker concurrency"
        )


__all__ = ["ParseFailureMessages"]
