# ====== Code Summary ======
# Provides DeviceResolver — a static-only helper that translates the BGE_DEVICE policy string
# ("auto" | "cuda" | "cpu") into a concrete device string FlagEmbedding accepts, and determines
# whether fp16 should actually be used.
#
# Key design decisions:
# - torch.cuda.is_available() is called LAZILY inside the method — no top-level torch import so
#   this module stays cheap to import in tests and tooling without triggering the ML stack.
# - fp16 is GATED to CUDA: if the resolved device is "cpu", fp16 is forced off and a warning is
#   logged — fp16 on CPU is a silent footgun (torch silently computes in fp32 anyway for most ops,
#   but FlagEmbedding may raise or produce NaNs depending on version).
# - "cuda" policy with no CUDA available raises RuntimeError at load time — no silent fallback.
#   The operator explicitly asked for GPU; silently running on CPU would mask a misconfiguration.

# ====== Standard Library Imports ======
from dataclasses import dataclass

# ====== Third-Party Library Imports ======
from loggerplusplus import loggerplusplus

# Accepted policy values — validated in BgeServerConfig.validate()
VALID_BGE_DEVICE_POLICIES: frozenset[str] = frozenset({"auto", "cuda", "cpu"})


@dataclass(frozen=True)
class ResolvedDevice:
    """
    Immutable result of device resolution.

    Attributes:
        device (str): Concrete device string to pass to FlagEmbedding ("cuda" or "cpu").
        use_fp16 (bool): Whether fp16 should actually be used after gating against the device.
    """

    device: str
    use_fp16: bool


class DeviceResolver:
    """
    Static helper that resolves a BGE_DEVICE policy into a concrete device + gated fp16 flag.

    Truth table:
      policy | cuda_available | resolved device | fp16 (when BGE_FP16=true)
      -------|----------------|-----------------|----------------------------
      auto   | yes            | cuda            | true
      auto   | no             | cpu             | false  (warning logged)
      cuda   | yes            | cuda            | true
      cuda   | no             | RuntimeError    | --
      cpu    | any            | cpu             | false  (warning if BGE_FP16=true)
    """

    logger = loggerplusplus.bind(identifier="DeviceResolver")

    # `-> None` is the project's static-only guard idiom (python.md); mypy's [misc] "must return an
    # instance" is a false positive, and `-> NoReturn` would make mypy treat the class as Never and
    # lose its @classmethods — so suppress just this check.
    def __new__(cls, *args: object, **kwargs: object) -> None:  # type: ignore[misc]
        raise TypeError(f"DeviceResolver is a static-only class and cannot be instantiated.")

    @classmethod
    def resolve(cls, policy: str, fp16_requested: bool) -> ResolvedDevice:
        """
        Resolve a device policy string into a concrete device and gated fp16 flag.

        The torch import is deferred into this method so the module can be imported cheaply
        without touching the ML stack. Call this only inside the FastAPI lifespan at boot time.

        Args:
            policy (str): BGE_DEVICE value — one of "auto", "cuda", "cpu".
            fp16_requested (bool): BGE_FP16 value from config.

        Returns:
            ResolvedDevice: The concrete device string and the gated fp16 flag.

        Raises:
            RuntimeError: When policy is "cuda" but torch.cuda.is_available() returns False.
            ValueError: When policy is not one of the accepted values (defensive; primary
                validation is in BgeServerConfig.validate()).
        """
        # 1. Reject unknown policies defensively (primary guard is in BgeServerConfig.validate)
        if policy not in VALID_BGE_DEVICE_POLICIES:
            raise ValueError(
                f"Unknown BGE_DEVICE policy '{policy}'. "
                f"Accepted values: {sorted(VALID_BGE_DEVICE_POLICIES)}"
            )

        # 2. Resolve the concrete device — defer torch import to here
        import torch  # noqa: PLC0415 (lazy import — keep ML stack out of module top-level)

        cuda_available = torch.cuda.is_available()
        cls.logger.debug(f"Device resolution: policy={policy}, cuda_available={cuda_available}")

        if policy == "cpu":
            device = "cpu"
        elif policy == "cuda":
            if not cuda_available:
                raise RuntimeError(
                    f"BGE_DEVICE=cuda was requested but torch.cuda.is_available() returned False. "
                    f"Either install a CUDA-enabled torch build or set BGE_DEVICE=auto to fall "
                    f"back to CPU automatically."
                )
            device = "cuda"
        else:
            # policy == "auto": prefer GPU when available, fall back to CPU silently
            device = "cuda" if cuda_available else "cpu"
            cls.logger.info(
                f"BGE_DEVICE=auto resolved -> {device} "
                f"(cuda_available={cuda_available})"
            )

        # 3. Gate fp16 to CUDA — fp16 on CPU is a footgun; warn and override
        if fp16_requested and device == "cpu":
            cls.logger.warning(
                f"BGE_FP16=true was requested but the resolved device is cpu. "
                f"fp16 is forced off — fp16 on CPU is not beneficial and may cause errors "
                f"depending on the FlagEmbedding version. "
                f"To use fp16, set BGE_DEVICE=cuda (requires a CUDA-capable host)."
            )
            use_fp16 = False
        else:
            use_fp16 = fp16_requested

        cls.logger.info(
            f"Device resolved: policy={policy} -> device={device}, use_fp16={use_fp16}"
        )
        return ResolvedDevice(device=device, use_fp16=use_fp16)
