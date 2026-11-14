# ====== Code Summary ======
# BgeModelsService: public facade over the two BGE model instances (BGEM3FlagModel for dense+sparse
# +colbert embedding and FlagReranker for cross-encoder reranking). It owns the model state
# (instances, resolved device, gated fp16, effective concurrency) and delegates the work to three
# units: BgeModelLoader (load), BgeEmbedEncoder (encode_*) and BgeRerankScorer
# (compute_rerank_scores_flat). Models are loaded lazily inside `load()` so that importing this
# module never triggers the heavy torch/FlagEmbedding import chain. Called exclusively from the
# FastAPI lifespan -- routes access it through CONTEXT.
#
# Device handling and revision pinning live in BgeModelLoader (see model_loader.py).

# ====== Standard Library Imports ======
from __future__ import annotations

from typing import TYPE_CHECKING, Any

# ====== Third-Party Library Imports ======
from loggerplusplus import LoggerClass

# ====== Local Project Imports ======
from .embed_encoder import BgeEmbedEncoder
from .model_loader import BgeModelLoader
from .rerank_scorer import BgeRerankScorer

# TYPE_CHECKING guard keeps the FlagEmbedding import out of the module's top-level scope;
# the actual import happens inside the loader's load() at boot time.
if TYPE_CHECKING:
    from FlagEmbedding import BGEM3FlagModel, FlagReranker


class BgeModelsService(LoggerClass):
    """
    Manages the lifecycle of the BGE embedding and reranking models.

    Both models are loaded once during FastAPI startup (via `load()`) and released cleanly
    at shutdown (via `unload()`). The heavy FlagEmbedding / torch import is deferred to
    `load()` so the module itself stays cheap to import for testing and tooling.

    Device selection is driven by the BGE_DEVICE policy: load() calls DeviceResolver.resolve()
    to get the concrete device and gated fp16 flag before constructing both models.
    """

    def __init__(
        self,
        embed_model_id: str,
        rerank_model_id: str,
        device_policy: str,
        fp16_requested: bool,
        torch_num_threads: int = 0,
        embed_revision: str | None = None,
        rerank_revision: str | None = None,
        load_reranker: bool = True,
        max_concurrent: int = 0,
    ) -> None:
        """
        Args:
            embed_model_id (str): HuggingFace model ID for BGEM3FlagModel (dense + sparse).
            rerank_model_id (str): HuggingFace model ID for FlagReranker (cross-encoder).
            device_policy (str): BGE_DEVICE policy — "auto", "cuda", or "cpu".
            fp16_requested (bool): BGE_FP16 from config. Gated: only applied on CUDA devices.
            torch_num_threads (int): Intra-op thread cap for torch (BGE_TORCH_NUM_THREADS).
                0 means "auto" — derived inside load() as ceil(cpu_budget / max_concurrency). The
                batching engine (libs/batching/engine.py) holds TWO independent locks — embed_lock
                (dense/sparse/colbert/embed_all) and rerank_lock (the separate FlagReranker
                instance) — so up to two model forward passes can legitimately run at once (one
                per lock) WHEN the reranker is loaded. Dividing the cpu_budget by max_concurrency
                keeps the combined intra-op thread usage of concurrent calls within the real core
                budget instead of each one alone claiming the full budget and doubling it under
                load.
                cpu_budget comes from CpuBudgetResolver — the cgroup v2 CFS quota when the
                process runs under one, else the scheduler affinity/cpu_count fallback.
                Stored here; applied at the start of load() before any torch model call.
            embed_revision (str | None): BGE_M3_REVISION — commit sha to pin the embed model
                to, or empty/None to keep the floating `main` behavior. Resolved to a local
                snapshot path by ModelRevisionResolver at the start of load().
            rerank_revision (str | None): BGE_RERANKER_REVISION — same as embed_revision, for
                the reranker.
            load_reranker (bool): BGE_LOAD_RERANKER from config. When False, load() skips
                constructing (and downloading) the FlagReranker entirely — for embed-only
                deployments that route production rerank to a hosted/GPU reranker instead.
                Defaults True to preserve the previous always-load behavior.
            max_concurrent (int): BGE_MAX_CONCURRENT — cap on simultaneous forward passes.
                0 = auto, resolved in load() once the device is known: 1 on CPU, else one per
                loaded model. The torch thread budget below divides by the RESOLVED value, so a
                cap of 1 hands the single running pass every core.
        """
        LoggerClass.__init__(self)
        self._load_reranker = load_reranker
        # The batching engine holds TWO independent locks (embed_lock + rerank_lock — see
        # libs/batching/engine.py), so up to two model forward passes can run concurrently:
        # one on embed_model (dense/sparse/colbert/embed_all) and one on the separate reranker
        # instance. Thread-count auto-derivation must budget for that real max concurrency — but
        # only when the reranker is actually loaded; rerank_lock is never contended on an
        # embed-only deployment (BGE_LOAD_RERANKER=false), so budgeting for it there would just
        # halve the embed thread pool for no reason.
        self._max_concurrency = 2 if load_reranker else 1

        self._loader = BgeModelLoader(
            embed_model_id=embed_model_id,
            rerank_model_id=rerank_model_id,
            device_policy=device_policy,
            fp16_requested=fp16_requested,
            torch_num_threads=torch_num_threads,
            embed_revision=embed_revision,
            rerank_revision=rerank_revision,
            load_reranker=load_reranker,
            max_concurrent=max_concurrent,
            initial_max_concurrency=self._max_concurrency,
        )
        # The encoder and scorer read the model/device through getters, so they always see the
        # service's current state (None before load(), the loaded instances after).
        self._encoder = BgeEmbedEncoder(lambda: self.embed_model, lambda: self._resolved_device)
        self._scorer = BgeRerankScorer(lambda: self.reranker, lambda: self._resolved_device)

        # Set by load() after device resolution; None until the service is started.
        self._resolved_device: str | None = None
        self._use_fp16: bool = False

        # Typed attributes set by load(); None until the service is started.
        self._embed_model: BGEM3FlagModel | None = None
        self._reranker: FlagReranker | None = None

    # ── Properties ────────────────────────────────────────────────────────────────

    @property
    def embed_model(self) -> Any:
        """
        Return the loaded BGEM3FlagModel instance.

        Raises:
            RuntimeError: If the service has not been started yet.
        """
        if self._embed_model is None:
            raise RuntimeError(f"BgeModelsService.load() has not been called yet.")
        return self._embed_model

    @property
    def reranker(self) -> Any:
        """
        Return the loaded FlagReranker instance.

        Raises:
            RuntimeError: If the service has not been started yet, or if the reranker was
                never loaded because BGE_LOAD_RERANKER=false (embed-only deployment).
        """
        if self._reranker is None:
            if not self._load_reranker:
                raise RuntimeError(
                    f"Reranker is not loaded (BGE_LOAD_RERANKER=false) — this deployment is "
                    f"embed-only."
                )
            raise RuntimeError(f"BgeModelsService.load() has not been called yet.")
        return self._reranker

    @property
    def max_concurrency(self) -> int:
        """Effective cap on simultaneous forward passes (final once load() has run)."""
        return self._max_concurrency

    @property
    def reranker_loaded(self) -> bool:
        """
        Return True once the reranker model is loaded.

        Always False when BGE_LOAD_RERANKER=false (the reranker is never constructed), and
        False before load() has completed. Routes use this to fail fast with a clean HTTP 503
        instead of letting a RuntimeError surface from deep inside the batching engine.

        Returns:
            bool: True when the reranker is loaded and ready to serve /rerank requests.
        """
        return self._reranker is not None

    @property
    def resolved_device(self) -> str | None:
        """
        Return the concrete device string used for both models, or None if not yet loaded.

        Returns:
            str | None: "cuda" or "cpu" after load(), None before.
        """
        return self._resolved_device

    @property
    def use_fp16(self) -> bool:
        """
        Return the GATED fp16 flag actually applied to the models.

        This is the value after device-gating (forced False on CPU even when BGE_FP16=true was
        requested), not the raw config request. Defaults to False until load() has run.

        Returns:
            bool: The effective fp16 flag — False before load(), the gated value after.
        """
        return self._use_fp16

    # ── Public methods ─────────────────────────────────────────────────────────────

    def load(self) -> None:
        """
        Resolve the device, then load the BGE embed model (and, unless gated off, the reranker).

        Delegates to BgeModelLoader (device resolution, torch thread cap, revision pinning,
        model construction) and stores the outcome on the service.

        Raises:
            RuntimeError: When device_policy="cuda" but CUDA is not available.
            Exception: Whatever huggingface_hub.snapshot_download raises (e.g. a network
                error) when a revision is pinned but the snapshot cannot be fetched -- a
                pinned deploy that cannot get its pinned weights must fail loudly, not fall
                back to the floating revision.
        """
        loaded = self._loader.load()
        self._resolved_device = loaded.device
        self._use_fp16 = loaded.use_fp16
        self._max_concurrency = loaded.max_concurrency
        self._embed_model = loaded.embed_model
        self._reranker = loaded.reranker

    def unload(self) -> None:
        """
        Release model references so the Python garbage collector can reclaim GPU/CPU memory.
        Safe to call even if `load()` was never reached (partial startup guard).
        """
        # 1. Drop references — GC handles the actual de-allocation
        self._embed_model = None
        self._reranker = None
        self.logger.info(f"BGE models unloaded")

    def encode_dense(self, texts: list[str], max_length: int) -> list[list[float]]:
        """
        Encode a batch of texts into dense L2-normalized vectors.

        Args:
            texts (list[str]): Texts to embed. Must be non-empty.
            max_length (int): Maximum token length for truncation.

        Returns:
            list[list[float]]: One 1024-dim float vector per input text.
        """
        return self._encoder.encode_dense(texts, max_length)

    def encode_sparse(
        self, texts: list[str], max_length: int
    ) -> list[list[dict[str, int | float]]]:
        """
        Encode a batch of texts into TEI-shaped sparse (lexical) token vectors.

        Args:
            texts (list[str]): Texts to embed. Must be non-empty.
            max_length (int): Maximum token length for truncation.

        Returns:
            list[list[dict]]: Per text, a list of ``{"index": token_id, "value": weight}`` dicts.
        """
        return self._encoder.encode_sparse(texts, max_length)

    def encode_dense_sparse(
        self, texts: list[str], max_length: int
    ) -> tuple[list[list[float]], list[list[dict[str, int | float]]]]:
        """
        Encode a batch of texts into BOTH dense and sparse vectors in ONE forward pass.

        Args:
            texts (list[str]): Texts to embed. Must be non-empty.
            max_length (int): Maximum token length for truncation.

        Returns:
            tuple[list[list[float]], list[list[dict]]]: A ``(dense, sparse)`` pair identical to
                calling ``encode_dense`` and ``encode_sparse`` separately.
        """
        return self._encoder.encode_dense_sparse(texts, max_length)

    def encode_colbert(self, texts: list[str], max_length: int) -> list[list[list[float]]]:
        """
        Encode a batch of texts into BGE-M3's native ColBERT multi-vector representation.

        Not part of the TEI contract -- an internal DocForge convention.

        Args:
            texts (list[str]): Texts to embed. Must be non-empty.
            max_length (int): Maximum token length for truncation.

        Returns:
            list[list[list[float]]]: Per input text, a list of per-token 1024-dim
                L2-normalized float vectors.
        """
        return self._encoder.encode_colbert(texts, max_length)

    def compute_rerank_scores_flat(self, pairs: list[list[str]]) -> list[float]:
        """
        Score a flat list of [query, text] pairs and return raw float scores.

        This is the batching-engine entry point: the engine builds the full pair list
        from multiple requests, calls this method once, then scatters the flat score
        list back to each request's future. Scores are sigmoid-normalized to [0, 1].

        Args:
            pairs (list[list[str]]): Each inner list is [query, candidate_text].
                Must be non-empty.

        Returns:
            list[float]: One sigmoid-normalized score per input pair, in input order.
        """
        return self._scorer.compute_rerank_scores_flat(pairs)
