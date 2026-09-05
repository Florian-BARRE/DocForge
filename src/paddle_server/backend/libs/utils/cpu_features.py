# ====== Code Summary ======
# Cheap, cached, Linux-safe probe for the CPU instruction-set features PaddlePaddle needs at runtime.
# The PaddlePaddle 3.x wheels are compiled with AVX and SIGILL (illegal instruction, exit 132) on the
# FIRST real inference when the host CPU lacks AVX — crucially, pipeline `build()` still succeeds, so
# the container would otherwise advertise readiness it cannot honor and then die mid-request. /health
# consults `supports_avx()` so a no-AVX host reports UNHEALTHY up front instead.
#
# The probe reads /proc/cpuinfo once and caches the result. Every failure mode (non-Linux, no /proc,
# unreadable, no flags line) degrades to "assume supported": we only ever fail readiness on a POSITIVE
# absence of AVX, never on an inability to probe — so a host we simply cannot inspect is never wrongly
# marked unhealthy. This never runs a real inference (that is what it exists to avoid).

# ====== Standard Library Imports ======
import pathlib

# ====== Third-Party Library Imports ======
from loggerplusplus import loggerplusplus


class CpuFeatures:
    """
    Static-only probe for CPU features PaddlePaddle requires. Never instantiated.

    The AVX result is computed once (first call) and cached for the process lifetime — CPU features
    do not change while the container runs.
    """

    logger = loggerplusplus.bind(identifier="CpuFeatures")

    # /proc/cpuinfo lists per-CPU feature flags on a line keyed "flags" (x86) or "Features" (ARM).
    _CPUINFO_PATH = pathlib.Path("/proc/cpuinfo")
    # Cached result of the AVX probe; None until the first `supports_avx()` call.
    _avx_supported: bool | None = None

    def __new__(cls, *args: object, **kwargs: object) -> "CpuFeatures":
        raise TypeError("CpuFeatures is a static-only class and cannot be instantiated.")

    @classmethod
    def supports_avx(cls) -> bool:
        """
        Whether this CPU exposes the AVX instruction set (required by the PaddlePaddle wheels).

        Returns:
            bool: True if AVX is present OR could not be positively ruled out; False only when
                /proc/cpuinfo was read and its flags line does NOT contain the `avx` token.
        """
        # 1. Probe once, then serve the cached answer — CPU features are fixed for the process.
        if cls._avx_supported is None:
            cls._avx_supported = cls._probe_avx()
        return cls._avx_supported

    @classmethod
    def _probe_avx(cls) -> bool:
        """
        Read /proc/cpuinfo and detect the `avx` feature flag, degrading safely on any read failure.

        Returns:
            bool: See `supports_avx()`.
        """
        # 1. Read /proc/cpuinfo — guarded: a non-Linux host, absent /proc or permission error means
        #    we cannot prove absence, so we assume AVX is present rather than block readiness.
        try:
            content = cls._CPUINFO_PATH.read_text(encoding="utf-8", errors="ignore")
        except OSError as exc:
            cls.logger.warning(
                f"Could not read {cls._CPUINFO_PATH} ({exc}); assuming AVX is present."
            )
            return True

        # 2. Scan the CPU flags line ("flags" on x86, "Features" on ARM) for the exact `avx` token
        #    (split-based match so it never confuses e.g. `avx512...` substrings with the base flag).
        for line in content.splitlines():
            if line.startswith(("flags", "Features")):
                has_avx = "avx" in line.split()
                if not has_avx:
                    cls.logger.error(
                        f"CPU lacks AVX — PaddlePaddle inference will SIGILL; reporting UNHEALTHY."
                    )
                return has_avx

        # 3. No flags line at all (unexpected architecture) — cannot prove absence, assume present.
        cls.logger.warning(
            f"No CPU flags line found in {cls._CPUINFO_PATH}; assuming AVX is present."
        )
        return True


__all__ = ["CpuFeatures"]
