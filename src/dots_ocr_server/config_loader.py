# ====== Code Summary ======
# DotsOcrServerConfig: the env-based settings of the dots.ocr per-element layout VLM micro-service. It
# extends the shared model_server_core ServerConfig (logging, host/port, DEV_MODE, gzip floor, request
# ceiling, lock-wait timeout), re-declaring the base fields the service has always read under a
# DOTS_OCR_* name, and adds the dots.ocr-specific knobs (model, rendering, smart-resize, GPU gate). The
# logging sinks are applied by the core's ServerEntrypoint, not at import time.
#
# Single runtime config, no YAML. No .env file is required at runtime; the service receives env vars
# directly from docker compose.

# ====== Third-Party Library Imports ======
from configplusplus import env
from model_server_core import ServerConfig


class DotsOcrServerConfig(ServerConfig):
    """
    Environment-driven configuration for the dots.ocr per-element layout VLM micro-service.

    All values are read from environment variables at class-evaluation time. No database or
    object-store credentials are needed — this service is a pure model host. All env vars have safe
    defaults so the container starts out-of-the-box without any .env file.
    """

    # ───── Model cache ─────
    # transformers resolves the dots.ocr weights (rednote-hilab/dots.ocr, ~3B) from HuggingFace on the
    # first parse and caches them under HF_HOME. Mounted as a named volume in compose so weights persist
    # across container recreations (mirrors bge_server's HF_HOME and mineru_server's model cache).
    # transformers reads HF_HOME itself; this value is surfaced in the boot log + used to pre-create the mount.
    DOTS_OCR_MODEL_CACHE_HOME: str = env("DOTS_OCR_MODEL_CACHE_HOME", default="/models")
    # HuggingFace model id (or a local path) transformers loads. dots.ocr's official weights repo.
    # Configurable so a first-GPU deploy can pin an exact revision or point at a local mirror without a rebuild.
    DOTS_OCR_MODEL_PATH: str = env("DOTS_OCR_MODEL_PATH", default="rednote-hilab/dots.ocr")

    # ───── Rendering ─────
    # DPI each PDF page is rasterised to before the smart-resize. Higher DPI = sharper small text
    # (better recognition) but larger images (slower inference, more VRAM). 200 DPI is a sensible
    # document default. The rendered page is then smart-resized (below); those RESIZED dims — not these
    # raw render dims — become the bbox normalization divisor.
    DOTS_OCR_RENDER_DPI: int = env("DOTS_OCR_RENDER_DPI", cast=int, default=200)
    # Hard ceiling on the number of pages parsed from one PDF — a runaway page count would exhaust GPU
    # time/VRAM. Pages beyond the cap are dropped (logged). 0 disables the cap.
    DOTS_OCR_MAX_PAGES: int = env("DOTS_OCR_MAX_PAGES", cast=int, default=0)
    # Max new tokens the VLM may emit per page (the JSON layout list). Large enough for a dense page.
    DOTS_OCR_MAX_TOKENS: int = env("DOTS_OCR_MAX_TOKENS", cast=int, default=16384)

    # ───── Smart-resize (Qwen2-VL) ─────
    # dots.ocr is a Qwen2-VL-family VLM: its image processor resizes every page to dims that are a
    # multiple of IMAGE_FACTOR and whose pixel count fits [MIN_PIXELS, MAX_PIXELS] BEFORE the encoder,
    # and returns bboxes in THAT resized frame. The sidecar resizes to the same dims itself (so those
    # dims are the honest bbox divisor) and pins MIN/MAX on the transformers processor so it does not
    # re-resize differently. Defaults follow the dots.ocr repo consts — verify against the model card on
    # first GPU deploy.
    DOTS_OCR_IMAGE_FACTOR: int = env("DOTS_OCR_IMAGE_FACTOR", cast=int, default=28)
    DOTS_OCR_MIN_PIXELS: int = env("DOTS_OCR_MIN_PIXELS", cast=int, default=3136)
    DOTS_OCR_MAX_PIXELS: int = env("DOTS_OCR_MAX_PIXELS", cast=int, default=11289600)

    # ───── Request limits (the core's MAX_BODY_BYTES, kept under its historical variable name) ─────
    # Hard ceiling (BYTES) on a request body the /parse route will buffer. The route reads the whole
    # body into memory (the body IS the PDF), so without a cap a multi-GB upload OOMs this container. A
    # declared Content-Length over the cap is rejected 413 before a byte is read; the streamed read is
    # capped too, so a lying/absent length can't bypass it. 100 MiB is generous for real scans/PDFs.
    MAX_BODY_BYTES: int = env("DOTS_OCR_MAX_BODY_BYTES", cast=int, default="104857600")

    # ───── Concurrency (the core's LOCK_WAIT_TIMEOUT_SECONDS, kept under its historical name) ─────
    # dots.ocr VLM inference is memory-heavy and not safe to run concurrently on one GPU, so every
    # /parse call is serialized behind a single asyncio.Lock. This is the max time a request waits to
    # acquire that lock before the router returns HTTP 503 (back-pressure) instead of piling up
    # unbounded. Defaults high — a per-page VLM parse of a multi-page document is minutes, not seconds.
    LOCK_WAIT_TIMEOUT_SECONDS: float = env(
        "DOTS_OCR_LOCK_WAIT_TIMEOUT_SECONDS", cast=float, default="590"
    )

    # ───── GPU gate ─────
    # dots.ocr's VLM requires CUDA — CPU is unsupported (transformers is not even installed on the cpu
    # build) and would fail at model load. When True (default), /health reports UNHEALTHY on a host with no
    # visible CUDA device so the container never advertises a readiness it cannot honor. Set False only
    # for a deliberate CPU smoke-test of the wiring (never for real parsing).
    DOTS_OCR_REQUIRE_GPU: bool = env("DOTS_OCR_REQUIRE_GPU", cast=bool, default="true")

    @classmethod
    def validate(cls) -> None:
        """
        Validate env-derived config values beyond simple type casting.

        Raises:
            ValueError: When a numeric knob is out of its valid range.
        """
        super().validate()
        if cls.DOTS_OCR_RENDER_DPI <= 0:
            raise ValueError(f"DOTS_OCR_RENDER_DPI must be > 0, got {cls.DOTS_OCR_RENDER_DPI}")
        if cls.DOTS_OCR_MAX_TOKENS <= 0:
            raise ValueError(f"DOTS_OCR_MAX_TOKENS must be > 0, got {cls.DOTS_OCR_MAX_TOKENS}")
        if cls.DOTS_OCR_IMAGE_FACTOR <= 0:
            raise ValueError(f"DOTS_OCR_IMAGE_FACTOR must be > 0, got {cls.DOTS_OCR_IMAGE_FACTOR}")
        if not 0 < cls.DOTS_OCR_MIN_PIXELS <= cls.DOTS_OCR_MAX_PIXELS:
            raise ValueError(
                f"require 0 < DOTS_OCR_MIN_PIXELS <= DOTS_OCR_MAX_PIXELS, got "
                f"{cls.DOTS_OCR_MIN_PIXELS} / {cls.DOTS_OCR_MAX_PIXELS}"
            )
