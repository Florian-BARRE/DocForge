# ====== Code Summary ======
# Provides CpuBudgetResolver — a static-only helper that resolves the EFFECTIVE CPU budget
# available to this process, honoring a cgroup v2 CFS quota when present.
#
# Why this exists: os.cpu_count() reports the HOST's core count, not the container's quota.
# On a host with 8 cores but a `docker run --cpus=4` (or compose `cpus: "4"`) limit, torch would
# set_num_threads(8) and run 2x oversubscribed against its real allotment, causing CPU thrash
# under load. Reading /sys/fs/cgroup/cpu.max gives the actual quota the kernel enforces.
#
# Key design decisions:
# - NEVER raises. Any read/parse failure (non-Linux, cgroup v1, rootless, missing file) degrades
#   to the sched_getaffinity/cpu_count fallback, logged at debug — a detection miss must never
#   crash startup.
# - The cgroup path is an optional parameter (defaults to the real /sys/fs/cgroup/cpu.max) so the
#   resolver stays a pure, easily-testable function — tests pass a tmp_path file instead of
#   mocking the filesystem.

# ====== Standard Library Imports ======
import os
import pathlib
from dataclasses import dataclass

# ====== Third-Party Library Imports ======
from loggerplusplus import loggerplusplus


@dataclass(frozen=True)
class ResolvedCpuBudget:
    """
    Immutable result of CPU budget resolution.

    Attributes:
        cpu_budget (int): Effective number of CPUs available to this process, minimum 1.
        source (str): Where the value came from — "cgroup" or "affinity".
    """

    cpu_budget: int
    source: str


class CpuBudgetResolver:
    """
    Static helper that resolves the effective CPU budget from the cgroup v2 CFS quota.

    Falls back to `os.sched_getaffinity(0)` (or `os.cpu_count()` when affinity is unavailable,
    e.g. non-Linux platforms) whenever the cgroup quota file is absent, unparseable, or reports
    no limit ("max").
    """

    logger = loggerplusplus.bind(identifier="CpuBudgetResolver")

    # Standard cgroup v2 location. cgroup v1 exposes the quota under a different path
    # (cpu.cfs_quota_us / cpu.cfs_period_us) — deliberately not handled here; it degrades
    # to the affinity fallback like any other unparseable/absent case.
    DEFAULT_CGROUP_CPU_MAX_PATH: pathlib.Path = pathlib.Path("/sys/fs/cgroup/cpu.max")

    def __new__(cls, *args: object, **kwargs: object) -> None:  # type: ignore[misc]
        raise TypeError(f"CpuBudgetResolver is a static-only class and cannot be instantiated.")

    @classmethod
    def resolve(cls, cgroup_cpu_max_path: pathlib.Path | None = None) -> ResolvedCpuBudget:
        """
        Resolve the effective CPU budget for this process.

        Args:
            cgroup_cpu_max_path (pathlib.Path | None): Override for the cgroup v2 cpu.max file
                path. Defaults to DEFAULT_CGROUP_CPU_MAX_PATH. Exposed for tests.

        Returns:
            ResolvedCpuBudget: The effective CPU count (>= 1) and which source produced it.
        """
        # 1. Try the cgroup v2 quota first — the accurate value inside a limited container.
        path = cgroup_cpu_max_path or cls.DEFAULT_CGROUP_CPU_MAX_PATH
        quota_budget = cls._read_cgroup_quota(path)
        if quota_budget is not None:
            cls.logger.debug(f"CPU budget resolved from cgroup quota at {path}: {quota_budget}")
            return ResolvedCpuBudget(cpu_budget=quota_budget, source="cgroup")

        # 2. No usable quota (absent file, "max"/unlimited, cgroup v1, non-Linux, parse error) —
        # fall back to the scheduler affinity mask, then the raw logical core count.
        fallback = cls._affinity_fallback()
        cls.logger.debug(f"CPU budget resolved from affinity/cpu_count fallback: {fallback}")
        return ResolvedCpuBudget(cpu_budget=fallback, source="affinity")

    @classmethod
    def _read_cgroup_quota(cls, path: pathlib.Path) -> int | None:
        """
        Read and parse a cgroup v2 cpu.max file into an effective CPU count.

        Args:
            path (pathlib.Path): Path to the cpu.max file, formatted "<quota> <period>".

        Returns:
            int | None: floor(quota / period), minimum 1 — or None when the file is missing,
                unreadable, malformed, or reports "max" (no quota / unlimited).
        """
        # Broad except is deliberate: any failure here (missing file, permission error, garbled
        # content, cgroup v1 layout) must degrade to the fallback, never abort startup.
        try:
            content = path.read_text().strip()
            quota_str, period_str = content.split()
            if quota_str == "max":
                return None
            quota, period = int(quota_str), int(period_str)
            if period <= 0:
                return None
            return max(1, quota // period)
        except Exception as exc:  # noqa: BLE001 — detection miss must never raise
            cls.logger.debug(f"cgroup cpu.max unreadable/unparseable at {path}: {exc}")
            return None

    @classmethod
    def _affinity_fallback(cls) -> int:
        """
        Return the scheduler-affinity CPU count, or `os.cpu_count()` when unavailable.

        Returns:
            int: Number of CPUs this process may run on, minimum 1.
        """
        if hasattr(os, "sched_getaffinity"):
            return len(os.sched_getaffinity(0))
        return os.cpu_count() or 1
