# ====== Code Summary ======
# CpuBudget: resolves the EFFECTIVE number of CPUs available to this process, honouring a cgroup v2 CFS
# quota when present. os.cpu_count() reports the HOST's cores, not the container's quota: on an 8-core
# host with `--cpus=4` an inference runtime would run 2x oversubscribed and thrash. Never raises: any
# read/parse failure (non-Linux, cgroup v1, rootless) degrades to the scheduler-affinity count.

# ====== Standard Library Imports ======
from __future__ import annotations

import os
import pathlib
from dataclasses import dataclass
from typing import Final

# ====== Third-Party Library Imports ======
from loggerplusplus import LoggerClass

# ====== Constants ======
DEFAULT_CGROUP_CPU_MAX_PATH: Final[pathlib.Path] = pathlib.Path("/sys/fs/cgroup/cpu.max")


@dataclass(frozen=True)
class ResolvedCpuBudget:
    """Immutable result of a CPU budget resolution.

    Attributes:
        cpu_budget (int): Effective CPU count, at least 1.
        source (str): `"cgroup"` or `"affinity"`.
    """

    cpu_budget: int
    source: str


class CpuBudget(LoggerClass):
    """Resolves the effective CPU budget of the process.

    Args:
        cgroup_cpu_max_path (pathlib.Path): The cgroup v2 `cpu.max` file; injectable for tests.
    """

    # Private attributes
    _cgroup_cpu_max_path: pathlib.Path

    def __init__(self, cgroup_cpu_max_path: pathlib.Path = DEFAULT_CGROUP_CPU_MAX_PATH) -> None:
        LoggerClass.__init__(self)
        self._cgroup_cpu_max_path = cgroup_cpu_max_path

    # =======================
    #   Private Methods
    # =======================
    def _read_cgroup_quota(self) -> int | None:
        """floor(quota / period) (minimum 1) from `cpu.max`; None on absent, "max" or garbled."""
        try:
            quota_text, period_text = self._cgroup_cpu_max_path.read_text().split()
            if quota_text == "max":
                return None
            quota, period = int(quota_text), int(period_text)
            if period <= 0:
                return None
            return max(1, quota // period)
        except (OSError, ValueError) as exc:
            self.logger.debug(f"cgroup cpu.max unreadable at {self._cgroup_cpu_max_path}: {exc}")
            return None

    @staticmethod
    def _affinity_count() -> int:
        """Scheduler-affinity CPU count, or the raw logical core count where it is unavailable."""
        if hasattr(os, "sched_getaffinity"):
            return max(1, len(os.sched_getaffinity(0)))
        return os.cpu_count() or 1

    # =======================
    #   Public Methods
    # =======================
    def resolve(self) -> ResolvedCpuBudget:
        """Resolve the effective CPU budget.

        Returns:
            ResolvedCpuBudget: The cgroup quota when one applies, else the affinity count.
        """
        quota = self._read_cgroup_quota()
        if quota is not None:
            return ResolvedCpuBudget(cpu_budget=quota, source="cgroup")
        return ResolvedCpuBudget(cpu_budget=self._affinity_count(), source="affinity")
