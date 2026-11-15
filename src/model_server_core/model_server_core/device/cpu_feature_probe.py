# ====== Code Summary ======
# CpuFeatureProbe: cheap, cached, Linux-safe probe for CPU instruction-set flags (e.g. "avx"). It reads
# /proc/cpuinfo once. Every failure mode (non-Linux, no /proc, unreadable, no flags line) degrades to
# "assume supported": a server only ever fails readiness on a POSITIVE absence of a flag, never on an
# inability to probe, so a host we cannot inspect is never wrongly marked unhealthy. It never runs a
# real inference. A server whose runtime SIGILLs without a flag (PaddlePaddle without AVX) overrides
# `ModelServer.health_blocker` with it.

# ====== Standard Library Imports ======
from __future__ import annotations

import pathlib

# ====== Third-Party Library Imports ======
from loggerplusplus import LoggerClass


class CpuFeatureProbe(LoggerClass):
    """Reports whether the CPU exposes a feature flag.

    Args:
        cpuinfo_path (pathlib.Path): The cpuinfo file; injectable so tests pass a temp file.
    """

    # Private attributes
    _cpuinfo_path: pathlib.Path
    _flags: frozenset[str] | None
    _flags_read: bool

    # `flags` on x86, `Features` on ARM.
    _FLAG_LINE_PREFIXES = ("flags", "Features")

    def __init__(self, cpuinfo_path: pathlib.Path = pathlib.Path("/proc/cpuinfo")) -> None:
        LoggerClass.__init__(self)
        self._cpuinfo_path = cpuinfo_path
        self._flags = None
        self._flags_read = False

    # =======================
    #   Private Methods
    # =======================
    def _read_flags(self) -> frozenset[str] | None:
        """Read the first flags line; None when it cannot be proven either way."""
        try:
            content = self._cpuinfo_path.read_text(encoding="utf-8", errors="ignore")
        except OSError as exc:
            self.logger.warning(f"Could not read {self._cpuinfo_path} ({exc}); assuming supported.")
            return None
        for line in content.splitlines():
            if line.startswith(self._FLAG_LINE_PREFIXES):
                return frozenset(line.partition(":")[2].split())
        self.logger.warning(f"No CPU flags line in {self._cpuinfo_path}; assuming supported.")
        return None

    # =======================
    #   Public Methods
    # =======================
    def supports(self, flag: str) -> bool:
        """Whether the CPU exposes `flag` (an exact token, never a substring like `avx512f`).

        Args:
            flag (str): Feature flag, as spelled in /proc/cpuinfo (`avx`, `avx2`...).

        Returns:
            bool: True if present OR not positively ruled out; False only when the flags line was
                read and does not contain the token.
        """
        if not self._flags_read:
            self._flags = self._read_flags()
            self._flags_read = True
        if self._flags is None:
            return True
        present = flag in self._flags
        if not present:
            self.logger.error(f"CPU lacks the '{flag}' flag.")
        return present
