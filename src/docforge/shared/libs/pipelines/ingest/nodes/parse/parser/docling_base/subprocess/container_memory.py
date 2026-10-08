# ====== Code Summary ======
# ContainerMemoryBudget — how much memory this process may really use: the cgroup v2 ``memory.max``
# of the container when one is set (what the kernel OOM-killer enforces), else the host's total RAM.
# The lower of the two wins (a cgroup limit above physical RAM is not a real budget). It is the base
# the parse RSS watchdog derives its default limit from (ParseRssLimit.auto_mb).

# ====== Standard Library Imports ======
import pathlib
from dataclasses import dataclass

# ====== Third-Party Library Imports ======
import psutil

# The cgroup v2 unified-hierarchy limit file as seen from inside the container's own namespace.
DEFAULT_CGROUP_MEMORY_MAX = pathlib.Path("/sys/fs/cgroup/memory.max")


@dataclass(frozen=True, slots=True)
class MemoryBudget:
    """A detected memory budget: its size and where it came from (for the startup log)."""

    total_bytes: int
    source: str


class ContainerMemoryBudget:
    """Static detector of the effective memory budget (cgroup v2 limit, else host RAM)."""

    def __new__(cls, *args: object, **kwargs: object) -> None:
        raise TypeError("ContainerMemoryBudget is a static-only class and cannot be instantiated.")

    @staticmethod
    def __cgroup_limit(path: pathlib.Path) -> int | None:
        """The cgroup v2 limit in bytes, or None when absent / unlimited ("max") / unreadable."""
        try:
            raw = path.read_text().strip()
        except OSError:
            return None
        if not raw.isdigit():
            return None
        return int(raw)

    @classmethod
    def detect(
        cls,
        cgroup_memory_max: pathlib.Path = DEFAULT_CGROUP_MEMORY_MAX,
        total_ram_bytes: int | None = None,
    ) -> MemoryBudget:
        """
        Detect the memory this process may use.

        Args:
            cgroup_memory_max (pathlib.Path): The cgroup v2 ``memory.max`` file to read.
            total_ram_bytes (int | None): Host RAM override (tests); None reads psutil.

        Returns:
            MemoryBudget: The cgroup limit when set and below RAM, else the host RAM.
        """
        # 1. Host RAM is the ceiling any limit is clamped to.
        ram = total_ram_bytes if total_ram_bytes is not None else psutil.virtual_memory().total
        # 2. A real cgroup v2 limit under RAM is what the OOM-killer enforces — it wins.
        limit = cls.__cgroup_limit(cgroup_memory_max)
        if limit is not None and limit < ram:
            return MemoryBudget(total_bytes=limit, source="cgroup memory.max")
        return MemoryBudget(total_bytes=ram, source="host RAM")


__all__ = ["ContainerMemoryBudget", "MemoryBudget"]
