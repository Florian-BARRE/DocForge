# ====== Code Summary ======
# BgeServerConfig: the env-based settings of the BGE model-suite micro-service. It extends the shared
# model_server_core ServerConfig (logging, host/port, DEV_MODE, gzip floor, device policy, thread
# budget), re-declaring the base fields the service has always read under a BGE_* name, and adds the
# BGE-specific knobs (model identities, revisions, batching, request ceilings). The logging sinks
# are applied by the core's ServerEntrypoint, not at import time.
#
# Single runtime config, no YAML. No .env file is required at runtime; the service receives env vars
# directly from docker compose.

# ====== Third-Party Library Imports ======
from configplusplus import env
from model_server_core import ServerConfig


class BgeServerConfig(ServerConfig):
    """
    Environment-driven configuration for the BGE model-suite micro-service.

    All values are read from environment variables at class-evaluation time. No database or
    object-store credentials are needed — this service is a pure model host. All env vars have
    safe defaults so the container starts out-of-the-box without any .env file.
    """

    # ───── BGE model identities ─────
    # HuggingFace model ID for the dense + sparse embedding model (BGEM3FlagModel).
    BGE_M3_MODEL: str = env("BGE_M3_MODEL", default="BAAI/bge-m3")
    # HuggingFace model ID for the cross-encoder reranker (FlagReranker).
    BGE_RERANKER_MODEL: str = env("BGE_RERANKER_MODEL", default="BAAI/bge-reranker-v2-m3")

    # ───── Reranker load gate ─────
    # When false, BgeModelsService.load() skips constructing (and downloading) the FlagReranker
    # entirely — no resident RAM for an unused model, no 30-120s reranker load time added to
    # startup. For embed-only deployments where production rerank is routed to a hosted/GPU
    # reranker via base_url override instead.
    # Defaults true to preserve current behavior — every existing deployment keeps loading the
    # reranker unless this is explicitly set false. POST /rerank returns a clean HTTP 503 when
    # the reranker isn't loaded, instead of crashing.
    BGE_LOAD_RERANKER: bool = env("BGE_LOAD_RERANKER", cast=bool, default="true")

    # ───── BGE model revision pins (supply-chain control) ─────
    # Commit sha each model is pinned to. BGEM3FlagModel/FlagReranker silently drop a `revision=`
    # kwarg (never forwarded to from_pretrained — see libs/bge_models/revision.py), so pinning
    # works by resolving the sha to a LOCAL snapshot path via huggingface_hub.snapshot_download
    # and loading from that path instead of the bare repo id.
    # Defaults are the `main`-branch head commit as of 2026-07-29 (`curl -s
    # https://huggingface.co/api/models/<repo> | jq .sha`) — a fresh deploy is pinned-by-default
    # but overridable. Set to "" (empty string) to opt back into the floating `main` behavior.
    BGE_M3_REVISION: str = env(
        "BGE_M3_REVISION", default="5617a9f61b028005a4858fdac845db406aefb181"
    )
    BGE_RERANKER_REVISION: str = env(
        "BGE_RERANKER_REVISION", default="953dc6f6f85a1b2dbfca4c34a2796e7dde08d41e"
    )

    # ───── BGE device policy ─────
    # Controls which compute device the models are loaded on (the core's DEVICE field, kept under
    # its historical BGE_DEVICE variable name).
    # "auto"  → prefer GPU if torch.cuda.is_available(), else fall back to CPU silently.
    # "cuda"  → require GPU; fail loud at load time if CUDA is not available (no silent fallback).
    # "cpu"   → always use CPU regardless of GPU availability.
    # DeviceResolver (libs/bge_models/device.py) translates this into a concrete device string.
    DEVICE: str = env("BGE_DEVICE", default="auto")

    # ───── BGE model runtime knobs ─────
    # Request fp16 precision. GATED: fp16 is only applied when the resolved device is "cuda".
    # If BGE_FP16=true but BGE_DEVICE resolves to "cpu", fp16 is forced off with a warning —
    # fp16 on CPU is not beneficial and may cause errors depending on the FlagEmbedding version.
    BGE_FP16: bool = env("BGE_FP16", cast=bool, default="false")
    # Maximum token length passed to FlagEmbedding's encode call. Default 2048 (was 8192): a single
    # oversized input at 8192 forces a full 8192-token transformer forward pass — a large transient
    # CPU + activation-RAM spike (a real OOM risk under the memory cap) and wasted work, since
    # contextualized chunks are far shorter. 2048 stays well above real chunk lengths; raise it only
    # if inputs are genuinely longer (embedding tokens beyond the chunk length yields nothing).
    BGE_M3_MAX_LENGTH: int = env("BGE_M3_MAX_LENGTH", cast=int, default="2048")

    # ───── Dynamic batching ─────
    # Maximum number of UNITS (texts for embed/sparse, query+text pairs for rerank) to include
    # in a single batch. A single request whose cost exceeds this limit is still admitted whole
    # and processed as a batch of one — FlagEmbedding handles its own internal chunking.
    # Effective range: 1..∞. With max_batch_size=1 + max_wait_ms=0 the engine degrades to
    # per-request processing (no batching overhead, useful for debugging or very low load).
    BGE_MAX_BATCH_SIZE: int = env("BGE_MAX_BATCH_SIZE", cast=int, default="32")
    # Batch formation window in milliseconds. After the first item arrives, the worker waits up
    # to this many ms for additional items before dispatching the batch. 0 = process immediately
    # with whatever is available (effectively disables wait-based batching).
    BGE_MAX_WAIT_MS: int = env("BGE_MAX_WAIT_MS", cast=int, default="10")
    # Maximum number of pending REQUESTS in the per-op bounded wait queue. When full, submit()
    # raises QueueFullError and the router responds HTTP 503 with Retry-After immediately. Kept
    # small on purpose: a long queue on a CPU host only holds work whose client will have timed
    # out before it runs. Raise it on a high-traffic GPU server.
    BGE_MAX_QUEUE_SIZE: int = env("BGE_MAX_QUEUE_SIZE", cast=int, default="8")
    # Retry-After (seconds) advertised on a 503 overload response.
    BGE_RETRY_AFTER_SECONDS: int = env("BGE_RETRY_AFTER_SECONDS", cast=int, default="2")
    # Maximum number of model forward passes in flight at once, ACROSS embed and rerank (a global
    # asyncio.Semaphore around inference). 0 = auto: 1 on a CPU device (one pass gets the whole
    # thread budget, no oversubscription), else one per loaded model (embed + rerank may overlap).
    BGE_MAX_CONCURRENT: int = env("BGE_MAX_CONCURRENT", cast=int, default="0")
    # Texts (or rerank pairs) per model call inside one formed batch. Between sub-batches the
    # engine drops work whose client has disconnected, so an abandoned batch stops at the next
    # boundary instead of grinding to the end. 0 = auto: 8 on CPU, no splitting elsewhere.
    BGE_SUB_BATCH_SIZE: int = env("BGE_SUB_BATCH_SIZE", cast=int, default="0")
    # Requests with at most this many texts/pairs (a search-query encode, a small rerank) ride a
    # priority lane and are served before queued bulk-ingest batches. 0 disables the lane.
    BGE_SMALL_REQUEST_MAX_ITEMS: int = env("BGE_SMALL_REQUEST_MAX_ITEMS", cast=int, default="4")
    # Seconds between client-disconnect polls while a request waits on the engine.
    BGE_DISCONNECT_POLL_SECONDS: float = env(
        "BGE_DISCONNECT_POLL_SECONDS", cast=float, default="0.25"
    )
    # Number of intra-op threads torch may use PER inference call (torch.set_num_threads) -- the
    # core's NUM_THREADS field, kept under its historical BGE_TORCH_NUM_THREADS variable name.
    # 0 = auto: the service derives a reasonable value at startup as cpu_count/max_concurrency
    # (rounded up, minimum 1) so the combined thread budget stays near the total core count.
    # Set explicitly to override the auto derivation (e.g. BGE_TORCH_NUM_THREADS=4).
    NUM_THREADS: int = env("BGE_TORCH_NUM_THREADS", cast=int, default="0")
    # Keep-warm interval in seconds. A background task runs a tiny forward pass on every model
    # (dense/sparse/rerank) every this-many seconds so their weights stay RESIDENT: on a
    # memory-constrained host the OS pages out an idle process's ~GB working set, and the next real
    # request then pays a 30-50 s page-in ("cold load"). That cold load occupies the single rerank
    # worker long enough that concurrent callers time out and re-enqueue, cascading. A cheap
    # periodic touch (~0.3 s of compute) prevents the eviction entirely. 0 = disabled.
    BGE_KEEPWARM_SECONDS: int = env("BGE_KEEPWARM_SECONDS", cast=int, default="45")

    # ───── Response compression (gzip) ─────
    # This service sits behind an internal docker-bridge link (bge_server <-> docforge app/worker),
    # not a public network -- bandwidth is not the bottleneck, CPU on the shared event loop is.
    # GZipMiddleware's default compresslevel is 9 (zlib's max), spent synchronously per response;
    # that's real CPU burned for marginal extra bytes saved over a cheap level on an internal hop.
    # Compression stays ON by default (still ~2x on the highly-repetitive float JSON) but at the
    # cheapest useful level -- raise BGE_GZIP_LEVEL or set BGE_GZIP_ENABLED=false if a future
    # deployment puts a real WAN hop in front of this service.
    BGE_GZIP_ENABLED: bool = env("BGE_GZIP_ENABLED", cast=bool, default="true")
    BGE_GZIP_LEVEL: int = env("BGE_GZIP_LEVEL", cast=int, default="1")

    # ───── Request size ceilings (edge validation, before the batching engine) ─────
    # A single oversized request is still admitted "whole" by BatchQueueWorker and holds the
    # shared model lock for its entire duration (see libs/batching/worker.py). These ceilings
    # reject such requests at the Pydantic layer (HTTP 422) instead of letting them stall every
    # other collection's embed/rerank traffic. Defaults scale off the batching/model knobs above
    # so they don't silently drift out of sync when those are tuned.
    #
    # Max number of items per request (inputs for /embed·/embed_sparse·/embed_colbert, texts for
    # /rerank). Default is 16x BGE_MAX_BATCH_SIZE: generous headroom over the DocForge embed node's
    # own client-side batch_size (default 32, see shared_libs embed/base/config.py) while still
    # bounding a misconfigured/unbounded caller.
    BGE_MAX_REQUEST_ITEMS: int = env(
        "BGE_MAX_REQUEST_ITEMS", cast=int, default=str(BGE_MAX_BATCH_SIZE * 16)
    )
    # Max characters per individual text (each /embed·/embed_sparse·/embed_colbert item, each
    # /rerank text or query). Default is 8x BGE_M3_MAX_LENGTH (tokens): truncate=True only
    # truncates AFTER tokenization, so an unbounded string still pays full tokenizer cost — this
    # caps that cost independently of the token truncation.
    BGE_MAX_TEXT_CHARS: int = env(
        "BGE_MAX_TEXT_CHARS", cast=int, default=str(BGE_M3_MAX_LENGTH * 8)
    )

    @classmethod
    def validate(cls) -> None:
        """
        Validate env-derived config values beyond simple type casting.

        Raises:
            ValueError: When a shared field is invalid (see ServerConfig.validate), or when any of
                the batching knobs has a value that would make the engine behave incorrectly
                (e.g. zero or negative batch size / queue size).
        """
        # The core validates the shared fields first (device policy, thread budget, limits).
        super().validate()
        if cls.BGE_MAX_BATCH_SIZE < 1:
            raise ValueError(f"BGE_MAX_BATCH_SIZE must be >= 1, got {cls.BGE_MAX_BATCH_SIZE}")
        if cls.BGE_MAX_WAIT_MS < 0:
            raise ValueError(f"BGE_MAX_WAIT_MS must be >= 0, got {cls.BGE_MAX_WAIT_MS}")
        if cls.BGE_MAX_QUEUE_SIZE < 1:
            raise ValueError(f"BGE_MAX_QUEUE_SIZE must be >= 1, got {cls.BGE_MAX_QUEUE_SIZE}")
        for knob in (
            "BGE_MAX_CONCURRENT",
            "BGE_SUB_BATCH_SIZE",
            "BGE_SMALL_REQUEST_MAX_ITEMS",
            "BGE_RETRY_AFTER_SECONDS",
        ):
            if getattr(cls, knob) < 0:
                raise ValueError(f"{knob} must be >= 0, got {getattr(cls, knob)}")
        if cls.BGE_DISCONNECT_POLL_SECONDS <= 0:
            raise ValueError(
                f"BGE_DISCONNECT_POLL_SECONDS must be > 0, got {cls.BGE_DISCONNECT_POLL_SECONDS}"
            )
        if cls.BGE_MAX_REQUEST_ITEMS < 1:
            raise ValueError(f"BGE_MAX_REQUEST_ITEMS must be >= 1, got {cls.BGE_MAX_REQUEST_ITEMS}")
        if cls.BGE_MAX_TEXT_CHARS < 1:
            raise ValueError(f"BGE_MAX_TEXT_CHARS must be >= 1, got {cls.BGE_MAX_TEXT_CHARS}")
        if cls.BGE_KEEPWARM_SECONDS < 0:
            raise ValueError(f"BGE_KEEPWARM_SECONDS must be >= 0, got {cls.BGE_KEEPWARM_SECONDS}")
        if not 1 <= cls.BGE_GZIP_LEVEL <= 9:
            raise ValueError(f"BGE_GZIP_LEVEL must be between 1 and 9, got {cls.BGE_GZIP_LEVEL}")
