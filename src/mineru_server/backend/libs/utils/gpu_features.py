# ====== Code Summary ======
# Cheap, cached probe for whether a CUDA GPU is visible to this container. MinerU2.5-Pro's VLM backend
# requires CUDA: on a host with no GPU it would fail at model load or run pathologically — so /health
# consults `cuda_available()` (gated by MINERU_REQUIRE_GPU) and reports UNHEALTHY up front, instead of
# advertising a readiness the container cannot honor and then failing mid-parse. This mirrors
# paddle_server's CpuFeatures (which gates on AVX for the same reason).
#
# Probe order (cheapest first, so the common GPU case never imports torch): the NVIDIA driver's
# /proc + /dev nodes, then a torch.cuda fallback. Every failure to probe degrades to "no GPU" —
# UNlike CpuFeatures (which assumes-present when it cannot prove absence), a POSITIVE GPU signal is
# required here, because running the VLM without CUDA is a hard failure, not a slow-but-safe path.

# ====== Standard Library Imports ======
import pathlib

# ====== Third-Party Library Imports ======
from loggerplusplus import loggerplusplus


class GpuFeatures:
    """
    Static-only probe for CUDA GPU visibility. Never instantiated.

    The result is computed once (first call) and cached for the process lifetime — the device set
    does not change while the container runs.
    """

    logger = loggerplusplus.bind(identifier="GpuFeatures")

    # The NVIDIA kernel driver exposes this file when a GPU + driver are present in the container.
    _NVIDIA_PROC = pathlib.Path("/proc/driver/nvidia/version")
    # Device nodes appear as /dev/nvidia0, /dev/nvidia1, ... when the container is granted GPUs.
    _DEV_DIR = pathlib.Path("/dev")
    # Cached probe result; None until the first `cuda_available()` call.
    _cuda_available: bool | None = None

    def __new__(cls, *args: object, **kwargs: object) -> "GpuFeatures":
        raise TypeError("GpuFeatures is a static-only class and cannot be instantiated.")

    @classmethod
    def cuda_available(cls) -> bool:
        """
        Whether a CUDA GPU is visible to this container.

        Returns:
            bool: True when the NVIDIA driver nodes are present OR torch reports CUDA available;
                False when no positive GPU signal could be found.
        """
        if cls._cuda_available is None:
            cls._cuda_available = cls._probe()
        return cls._cuda_available

    @classmethod
    def device(cls) -> str:
        """
        The runtime compute device string, derived from CUDA visibility (memoized via cuda_available).

        Feeds the GET /health `device` field, which the DocForge app's GET /capabilities probe reads
        (it checks `device == "cuda"`). The value is exactly "cuda" or "cpu".

        Returns:
            str: "cuda" when a CUDA GPU is visible, else "cpu".
        """
        return "cuda" if cls.cuda_available() else "cpu"

    @classmethod
    def _probe(cls) -> bool:
        """
        Detect a CUDA GPU cheaply (driver nodes), falling back to torch.cuda, degrading to False.

        Returns:
            bool: See `cuda_available()`.
        """
        # 1. Cheapest signal: the NVIDIA driver's /proc version file exists when a GPU is present.
        try:
            if cls._NVIDIA_PROC.exists():
                return True
        except OSError:
            pass

        # 2. GPU device nodes granted to the container (/dev/nvidia0, ...).
        try:
            if any(node.name.startswith("nvidia") for node in cls._DEV_DIR.iterdir()):
                return True
        except OSError:
            pass

        # 3. Fallback: ask torch directly (heavier — imports torch). A missing torch or any error means
        #    no runnable CUDA, so degrade to False (the honest answer for a VLM that needs CUDA).
        try:
            import torch  # noqa: PLC0415

            if torch.cuda.is_available():
                return True
        except Exception as exc:  # noqa: BLE001 — any probe failure is treated as "no GPU"
            cls.logger.warning(f"torch CUDA probe failed ({exc}); reporting no GPU.")

        cls.logger.error(
            f"No CUDA GPU detected — MinerU's VLM backend requires one; reporting UNHEALTHY."
        )
        return False


__all__ = ["GpuFeatures"]
