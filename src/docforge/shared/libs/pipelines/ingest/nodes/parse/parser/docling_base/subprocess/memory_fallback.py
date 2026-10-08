# ====== Code Summary ======
# ParseMemoryFallback — the deployment-wide default for the parse subprocess' address-space cap. A
# collection's ``parse_memory_mb`` of 0 means "use this fallback", and the fallback itself is OFF (0 =
# no cap) by default: RLIMIT_AS bounds VIRTUAL memory, which torch/onnxruntime over-reserve, so a sized
# default broke the layout model's mmap on real PDFs. An operator opts in by sizing
# RUNTIME_CONFIG.WORKER_PARSE_MEMORY_MB (installed by the worker edge at startup) after measuring the
# parse child's VmPeak; the node resolves "collection value, else deployment fallback" here. The
# default-ON memory guard is the parent's RESIDENT-memory watchdog (ParseRssLimit), not this cap. Pure: the shared lib never reads worker config,
# and the default blob is untouched (the knob stays 0 in it — no ENGINE_BLOB_VERSION bump).


class ParseMemoryFallback:
    """Process-wide fallback cap (MiB) applied when a node's ``parse_memory_mb`` is 0."""

    _fallback_mb: int = 0

    @classmethod
    def install(cls, memory_mb: int) -> None:
        """Set the fallback (worker startup). 0 = no fallback (the historical uncapped behaviour)."""
        cls._fallback_mb = max(0, int(memory_mb))

    @classmethod
    def resolve(cls, configured_mb: int, applies: bool = True) -> int:
        """
        The effective cap for one parse.

        Args:
            configured_mb (int): The node's ``parse_memory_mb`` (0 = unset).
            applies (bool): False for a parser where an RLIMIT_AS cap is harmful (the GPU/CUDA granite
                VLM, whose large virtual reservations a cap would break) — it then keeps its own value.

        Returns:
            int: ``configured_mb`` when set (a collection can always override), else the fallback.
        """
        if configured_mb > 0 or not applies:
            return configured_mb
        return cls._fallback_mb


__all__ = ["ParseMemoryFallback"]
