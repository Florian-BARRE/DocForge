# ====== Code Summary ======
# Cheap, cached probe reporting the compute device this container runs on ("cuda" or "cpu"). It feeds
# the GET /health `device` field, which the DocForge app's GET /capabilities probe reads to decide
# whether a GPU is present (it checks `device == "cuda"`). The value MUST be exactly "cuda" or "cpu".
#
# This sidecar runs on PaddlePaddle (NOT torch), so the probe uses Paddle's own runtime GPU check:
# a CUDA-compiled wheel WITH at least one visible device. The probe is GUARDED: the -cpu wiring image
# ships the CPU wheel and any probe failure degrades to "cpu" — a health probe must never raise, and
# "cpu" is the safe, honest answer when a GPU cannot be proven present. We report "cuda" (never "gpu")
# to match the shared cross-sidecar contract.

# ====== Third-Party Library Imports ======
from loggerplusplus import loggerplusplus


class DeviceProbe:
    """
    Static-only probe for the runtime compute device. Never instantiated.

    The result is computed once (first call) and cached for the process lifetime — the device set
    does not change while the container runs.
    """

    logger = loggerplusplus.bind(identifier="DeviceProbe")

    # Cached probe result; None until the first `device()` call.
    _device: str | None = None

    def __new__(cls, *args: object, **kwargs: object) -> "DeviceProbe":
        raise TypeError("DeviceProbe is a static-only class and cannot be instantiated.")

    @classmethod
    def device(cls) -> str:
        """
        The runtime compute device, memoized.

        Returns:
            str: "cuda" when PaddlePaddle is CUDA-compiled and at least one GPU is visible; "cpu"
                otherwise (including when paddle is not importable or the probe fails).
        """
        if cls._device is None:
            cls._device = cls._probe()
        return cls._device

    @classmethod
    def _probe(cls) -> str:
        """
        Detect the compute device via PaddlePaddle, degrading to "cpu" on any failure.

        Returns:
            str: See `device()`.
        """
        try:
            import paddle  # noqa: PLC0415

            gpu_present = (
                paddle.device.is_compiled_with_cuda() and paddle.device.cuda.device_count() > 0
            )
            return "cuda" if gpu_present else "cpu"
        except Exception as exc:  # noqa: BLE001 — any probe failure degrades to "cpu"
            cls.logger.warning(f"paddle device probe failed ({exc}); reporting 'cpu'.")
            return "cpu"


__all__ = ["DeviceProbe"]
