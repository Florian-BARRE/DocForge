# ====== Code Summary ======
# ParseRssLimit — the deployment-wide RESIDENT-memory limit the parent's watchdog enforces on the
# docling/granite parse subprocess tree. Unlike RLIMIT_AS (virtual, which torch/onnx over-reserve),
# RSS tracks what the kernel OOM-killer actually counts, so a sane default can ship ON. The worker
# edge resolves WORKER_PARSE_RSS_LIMIT_MB at startup (-1 = auto, 0 = off, >0 = explicit MiB) and
# installs it here; a node resolves "collection parse_rss_limit_mb, else this default". Pure: the
# shared lib never reads worker config.
#
# Auto default = 80% of the memory budget (cgroup v2 memory.max, else host RAM) minus a 1 GiB reserve
# for the worker process itself, never below half the budget (so a small container still gets a
# limit the child can load its models under, rather than one that kills every parse).

# ====== Local Project Imports ======
from .container_memory import MemoryBudget

_MIB = 1024 * 1024


class ParseRssLimit:
    """Process-wide default RSS limit (MiB) applied when a node's ``parse_rss_limit_mb`` is 0."""

    # The share of the budget the parse tree may hold, the worker's own reserve, and the floor share.
    AUTO_FRACTION: float = 0.8
    WORKER_RESERVE_MB: int = 1024
    FLOOR_FRACTION: float = 0.5
    # The WORKER_PARSE_RSS_LIMIT_MB sentinel that asks for the auto-derived default.
    AUTO: int = -1

    _default_mb: int = 0

    @classmethod
    def auto_mb(cls, budget: MemoryBudget) -> int:
        """
        The auto-derived limit for a memory budget.

        Args:
            budget (MemoryBudget): The detected container/host memory budget.

        Returns:
            int: ``max(budget*0.8 - 1024, budget*0.5)`` in MiB.
        """
        budget_mb = budget.total_bytes // _MIB
        derived = int(budget_mb * cls.AUTO_FRACTION) - cls.WORKER_RESERVE_MB
        return max(derived, int(budget_mb * cls.FLOOR_FRACTION))

    @classmethod
    def from_setting(cls, setting_mb: int, budget: MemoryBudget) -> int:
        """
        Turn the WORKER_PARSE_RSS_LIMIT_MB setting into an effective limit.

        Args:
            setting_mb (int): -1 (auto), 0 (watchdog off) or an explicit limit in MiB.
            budget (MemoryBudget): The detected budget the auto mode derives from.

        Returns:
            int: The effective deployment limit in MiB (0 = off).
        """
        if setting_mb == cls.AUTO:
            return cls.auto_mb(budget)
        return max(0, int(setting_mb))

    @classmethod
    def install(cls, limit_mb: int) -> None:
        """Set the deployment default (worker startup). 0 = watchdog off."""
        cls._default_mb = max(0, int(limit_mb))

    @classmethod
    def resolve(cls, configured_mb: int) -> int:
        """
        The effective RSS limit for one parse.

        Args:
            configured_mb (int): The node's ``parse_rss_limit_mb`` (0 = unset).

        Returns:
            int: ``configured_mb`` when set (a collection can always override), else the default.
        """
        return configured_mb if configured_mb > 0 else cls._default_mb


__all__ = ["ParseRssLimit"]
