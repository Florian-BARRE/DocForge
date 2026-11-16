# ====== Code Summary ======
# PaddleServerConfig: the env-based settings of the PP-StructureV3 / PaddleOCR / PaddleOCR-VL
# layout-parsing micro-service. It extends the shared model_server_core ServerConfig (logging,
# host/port, DEV_MODE, gzip floor, request ceiling, lock-wait timeout), re-declaring the base fields
# the service has always read under a PADDLE_* name, and adds the Paddle-specific knobs (model cache,
# sub-pipeline toggles, OCR language). The logging sinks are applied by the core's ServerEntrypoint,
# not at import time.
#
# Single runtime config, no YAML. No .env file is required at runtime; the service receives env vars
# directly from docker compose.

# ====== Third-Party Library Imports ======
from configplusplus import env
from model_server_core import ServerConfig


class PaddleServerConfig(ServerConfig):
    """
    Environment-driven configuration for the PP-StructureV3 layout-parsing micro-service.

    All values are read from environment variables at class-evaluation time. No database or
    object-store credentials are needed — this service is a pure model host. All env vars have
    safe defaults so the container starts out-of-the-box without any .env file.
    """

    # ───── Model cache ─────
    # PaddleX resolves every inference model (layout/OCR/table/formula/seal) to a tarball fetched
    # from the configured model hoster on first use and cached under
    # ``{PADDLE_PDX_CACHE_HOME}/official_models`` (paddlex.utils.cache.CACHE_DIR /
    # paddlex.inference.utils.official_models._save_dir — verified against the paddlex 3.7.0
    # wheel source, NOT documented in the pipeline usage tutorials). Mounted as a named volume in
    # compose so weights persist across container recreations (mirrors bge_server's HF_HOME).
    PADDLE_PDX_CACHE_HOME: str = env("PADDLE_PDX_CACHE_HOME", default="/models")
    # Model hoster: "huggingface" (default, needs huggingface.co resolution — same DNS pin as
    # bge_server) or "bos"/"aistudio"/"modelscope". Read here only to surface it in the boot log;
    # PaddleX itself reads the env var directly (paddlex.utils.flags.MODEL_SOURCE).
    PADDLE_PDX_MODEL_SOURCE: str = env("PADDLE_PDX_MODEL_SOURCE", default="huggingface")

    # ───── Request limits (the core's MAX_BODY_BYTES, kept under its historical variable name) ─────
    # Hard ceiling (BYTES) on a request body the /ocr, /layout-parsing and /vl-parse routes will buffer. Both
    # read the whole body into memory (the body IS the image/PDF), so without a cap a multi-GB upload
    # OOMs this container (whose memory ceiling exists for model spikes, not attacker payloads). A
    # declared Content-Length over the cap is rejected 413 before a byte is read; the streamed read is
    # capped too, so a lying/absent length can't bypass it. 100 MiB is generous for real scans/PDFs.
    MAX_BODY_BYTES: int = env("PADDLE_MAX_BODY_BYTES", cast=int, default="104857600")

    # ───── PP-StructureV3 sub-pipeline toggles (lean default) ─────
    # Mandatory sub-pipelines (layout detection + general OCR) are always on — PaddleX has no
    # toggle for them. These four are the OPTIONAL sub-pipelines; env-driven so the same image
    # runs lean or full without a rebuild.
    PADDLE_USE_TABLE_RECOGNITION: bool = env(
        "PADDLE_USE_TABLE_RECOGNITION", cast=bool, default="true"
    )
    PADDLE_USE_FORMULA_RECOGNITION: bool = env(
        "PADDLE_USE_FORMULA_RECOGNITION", cast=bool, default="false"
    )
    PADDLE_USE_SEAL_RECOGNITION: bool = env(
        "PADDLE_USE_SEAL_RECOGNITION", cast=bool, default="false"
    )
    PADDLE_USE_DOC_ORIENTATION_CLASSIFY: bool = env(
        "PADDLE_USE_DOC_ORIENTATION_CLASSIFY", cast=bool, default="false"
    )
    # NOTE: there is deliberately NO PADDLE_USE_DOC_UNWARPING knob. Doc-unwarping is forced OFF
    # unconditionally in both pipelines (see libs/ppstructure/service.py) because the mapper's
    # bbox provenance contract assumes the layout-detection image is the raw rendered page, not a
    # geometrically unwarped one. An env override here would be a lie — it could not be honored
    # without breaking that invariant — so it is not offered.

    # ───── PaddleOCR (OCR-only pipeline) ─────
    # The OCR-only capability runs a SEPARATE PaddleOCR (text detection + recognition) instance,
    # independent of the PP-StructureV3 layout pipeline above. These knobs are set at build time
    # (no request-level override), so the same image runs any language without a rebuild.
    # Recognition language pack (e.g. "en", "fr", "ch") — selects the det+rec model pair.
    PADDLE_OCR_LANG: str = env("PADDLE_OCR_LANG", default="en")
    # Run the textline-orientation classifier before recognition — helps rotated lines at the cost
    # of an extra model + latency. OFF by default (born-digital crops are upright).
    PADDLE_OCR_USE_TEXTLINE_ORIENTATION: bool = env(
        "PADDLE_OCR_USE_TEXTLINE_ORIENTATION", cast=bool, default="false"
    )

    # ───── Concurrency (the core's LOCK_WAIT_TIMEOUT_SECONDS, kept under its historical name) ─────
    # PaddlePaddle inference is not thread-safe; every /layout-parsing call is serialized behind
    # a single asyncio.Lock (libs/ppstructure/service.py). This is the max time a request waits
    # to acquire that lock before the router returns HTTP 503 (back-pressure, same shape as
    # bge_server's queue-full 503) instead of piling up unbounded.
    LOCK_WAIT_TIMEOUT_SECONDS: float = env(
        "PADDLE_LOCK_WAIT_TIMEOUT_SECONDS", cast=float, default="290"
    )
