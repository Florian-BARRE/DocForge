# ====== Code Summary ======
# Owns the two BGE model instances (BGEM3FlagModel for dense+sparse embedding and FlagReranker
# for cross-encoder reranking). Models are loaded lazily inside `load()` so that importing this
# module never triggers the heavy torch/FlagEmbedding import chain. Called exclusively from the
# FastAPI lifespan — routes access it through CONTEXT.
#
# Device handling: load() calls DeviceResolver.resolve() to translate the BGE_DEVICE policy
# ("auto"|"cuda"|"cpu") into a concrete device string and gated fp16 flag. Both models receive
# the resolved device via the `devices=` parameter that FlagEmbedding accepts.

# ====== Standard Library Imports ======
from __future__ import annotations

import math
import os
import time
from typing import TYPE_CHECKING, Any

# ====== Third-Party Library Imports ======
from loggerplusplus import LoggerClass

# ====== Local Project Imports ======
from .device import DeviceResolver

# TYPE_CHECKING guard keeps the FlagEmbedding import out of the module's top-level scope;
# the actual import happens inside load() at boot time.
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
    ) -> None:
        """
        Args:
            embed_model_id (str): HuggingFace model ID for BGEM3FlagModel (dense + sparse).
            rerank_model_id (str): HuggingFace model ID for FlagReranker (cross-encoder).
            device_policy (str): BGE_DEVICE policy — "auto", "cuda", or "cpu".
            fp16_requested (bool): BGE_FP16 from config. Gated: only applied on CUDA devices.
            torch_num_threads (int): Intra-op thread cap for torch (BGE_TORCH_NUM_THREADS).
                0 means "auto" — derived inside load() as ceil(cpu_count / 1) since the
                batching engine serialises model calls via a single asyncio.Lock. The engine
                is the concurrency gate now; the service no longer needs a concurrency hint.
                Stored here; applied at the start of load() before any torch model call.
        """
        LoggerClass.__init__(self)
        self._embed_model_id = embed_model_id
        self._rerank_model_id = rerank_model_id
        self._device_policy = device_policy
        self._fp16_requested = fp16_requested
        self._torch_num_threads = torch_num_threads
        # The batching engine's model_lock ensures at most one model call runs at a time,
        # so the effective concurrency for thread-count auto-derivation is always 1.
        self._max_concurrency = 1

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
            RuntimeError: If the service has not been started yet.
        """
        if self._reranker is None:
            raise RuntimeError(f"BgeModelsService.load() has not been called yet.")
        return self._reranker

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
        Resolve the device, then load both BGE models into memory.

        Steps:
          1. Call DeviceResolver.resolve() to translate the BGE_DEVICE policy into a concrete
             device string and gated fp16 flag (torch.cuda.is_available() is called here).
          2. Import FlagEmbedding (deferred — avoids ML stack at module import time).
          3. Construct BGEM3FlagModel with the resolved device and fp16 flag.
          4. Construct FlagReranker with the same device and fp16 flag.

        Raises:
            RuntimeError: When device_policy="cuda" but CUDA is not available.
        """
        # 1. Resolve device policy -> concrete device + gated fp16
        # DeviceResolver defers the torch import inside resolve(), consistent with the
        # deferred-ML-import rule for this service.
        resolved = DeviceResolver.resolve(self._device_policy, self._fp16_requested)
        self._resolved_device = resolved.device
        self._use_fp16 = resolved.use_fp16

        self.logger.info(
            f"Device policy '{self._device_policy}' resolved -> "
            f"device={resolved.device}, use_fp16={resolved.use_fp16}"
        )

        # 2. Defer the heavy FlagEmbedding import to this moment — the container is booting.
        # Torch is bundled with FlagEmbedding, so import it here too, right after, to apply
        # the thread cap before any model is instantiated.
        from FlagEmbedding import BGEM3FlagModel, FlagReranker  # noqa: PLC0415
        import torch  # noqa: PLC0415

        # 3. Cap torch intra-op threads to prevent CPU oversubscription under concurrent load.
        # When N requests each spawn torch thread pools across all cores, the OS scheduler
        # thrashes and latency explodes non-linearly. The cap distributes available cores
        # across the allowed concurrent calls (see BGE_MAX_CONCURRENCY / the semaphore).
        # Only relevant on CPU; on CUDA this has no meaningful effect but is harmless.
        if self._torch_num_threads > 0:
            # Explicit override from BGE_TORCH_NUM_THREADS.
            n_threads = self._torch_num_threads
        else:
            # Auto: share cores evenly across concurrent slots, minimum 1.
            cpu_count = os.cpu_count() or 1
            n_threads = max(1, math.ceil(cpu_count / max(1, self._max_concurrency)))
        torch.set_num_threads(n_threads)
        self.logger.info(
            f"torch intra-op threads set to {n_threads} "
            f"(BGE_TORCH_NUM_THREADS={self._torch_num_threads}, "
            f"max_concurrency={self._max_concurrency}, "
            f"cpu_count={os.cpu_count() or 1})"
        )

        # 4. Load the embedding model (dense + sparse heads both available from one instance).
        # The `devices` parameter accepts a device string ("cuda" / "cpu") or list thereof.
        self.logger.info(
            f"Loading embed model: {self._embed_model_id} "
            f"(device={resolved.device}, fp16={resolved.use_fp16})"
        )
        self._embed_model = BGEM3FlagModel(
            self._embed_model_id,
            use_fp16=resolved.use_fp16,
            devices=resolved.device,
        )
        self.logger.info(f"Embed model loaded -> {self._embed_model_id}")

        # 5. Load the cross-encoder reranker with the same device settings.
        self.logger.info(
            f"Loading reranker: {self._rerank_model_id} "
            f"(device={resolved.device}, fp16={resolved.use_fp16})"
        )
        self._reranker = FlagReranker(
            self._rerank_model_id,
            use_fp16=resolved.use_fp16,
            devices=resolved.device,
        )
        self.logger.info(f"Reranker loaded -> {self._rerank_model_id}")

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
        device = self._resolved_device or "unknown"
        n = len(texts)
        self.logger.debug(f"encode_dense: {n} texts, max_length={max_length}, device={device}")

        # 1. Run encode requesting only the dense head; time the model call itself
        t0 = time.perf_counter()
        out = self.embed_model.encode(
            texts,
            return_dense=True,
            return_sparse=False,
            return_colbert_vecs=False,
            max_length=max_length,
        )
        elapsed = time.perf_counter() - t0

        # 2. Convert numpy arrays to plain Python lists (JSON-serialisable)
        result = [vec.tolist() for vec in out["dense_vecs"]]
        self.logger.debug(
            f"encode_dense: {n} texts -> {len(result)} vecs in {elapsed:.3f}s (device={device})"
        )
        return result

    def encode_sparse(
        self, texts: list[str], max_length: int
    ) -> list[list[dict[str, int | float]]]:
        """
        Encode a batch of texts into TEI-shaped sparse (lexical) token vectors.

        BGE-M3 returns a ``{token_id(str): weight(float)}`` dict per text; this method
        re-shapes to the TEI contract ``[{"index": int, "value": float}, ...]`` so the
        DocForge ``tei`` provider parses it without modification.

        Args:
            texts (list[str]): Texts to embed. Must be non-empty.
            max_length (int): Maximum token length for truncation.

        Returns:
            list[list[dict]]: Per text, a list of ``{"index": token_id, "value": weight}`` dicts.
        """
        device = self._resolved_device or "unknown"
        n = len(texts)
        self.logger.debug(f"encode_sparse: {n} texts, max_length={max_length}, device={device}")

        # 1. Run encode requesting only the sparse head; time the model call itself
        t0 = time.perf_counter()
        out = self.embed_model.encode(
            texts,
            return_dense=False,
            return_sparse=True,
            return_colbert_vecs=False,
            max_length=max_length,
        )
        elapsed = time.perf_counter() - t0

        # 2. Re-shape from BGE-M3 internal dict to TEI index/value token list
        result: list[list[dict[str, int | float]]] = []
        for weights in out["lexical_weights"]:
            result.append([{"index": int(tok), "value": float(w)} for tok, w in weights.items()])

        self.logger.debug(
            f"encode_sparse: {n} texts -> {len(result)} token-lists in {elapsed:.3f}s (device={device})"
        )
        return result

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
        device = self._resolved_device or "unknown"
        n = len(pairs)
        self.logger.debug(f"compute_rerank_scores_flat: {n} pairs, device={device}")

        # 1. Time the scoring call
        t0 = time.perf_counter()
        scores = self.reranker.compute_score(pairs, normalize=True)
        elapsed = time.perf_counter() - t0

        # 2. Normalise to list — compute_score returns a scalar when n=1
        if not isinstance(scores, list):
            scores = [scores]

        self.logger.debug(
            f"compute_rerank_scores_flat: {n} pairs -> {len(scores)} scores in {elapsed:.3f}s (device={device})"
        )
        return [float(s) for s in scores]

    def compute_rerank_scores(
        self, query: str, texts: list[str]
    ) -> list[dict[str, int | float]]:
        """
        Score each candidate text against the query and return TEI-shaped results.

        Scores are sigmoid-normalized to [0, 1] for stable threshold comparison. Results are
        returned in INPUT order — the DocForge ``bge_reranker`` provider re-sorts by index.

        Args:
            query (str): The search query.
            texts (list[str]): Candidate texts to score against the query. Must be non-empty.

        Returns:
            list[dict]: One ``{"index": i, "score": float}`` per candidate, in input order.
        """
        device = self._resolved_device or "unknown"
        n = len(texts)
        self.logger.debug(f"compute_rerank_scores: {n} candidates, device={device}")

        # 1. Build (query, text) pairs for the cross-encoder
        pairs = [[query, text] for text in texts]

        # 2. Time the scoring call; compute_score returns a bare float for a single pair
        t0 = time.perf_counter()
        scores = self.reranker.compute_score(pairs, normalize=True)
        elapsed = time.perf_counter() - t0

        if not isinstance(scores, list):
            scores = [scores]

        # 3. Wrap as index/score dicts aligned with the input order
        result = [{"index": i, "score": float(s)} for i, s in enumerate(scores)]
        self.logger.debug(
            f"compute_rerank_scores: {n} candidates -> {len(result)} scores in {elapsed:.3f}s (device={device})"
        )
        return result
