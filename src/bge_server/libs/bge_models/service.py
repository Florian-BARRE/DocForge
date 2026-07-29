# ====== Code Summary ======
# Owns the two BGE model instances (BGEM3FlagModel for dense+sparse embedding and FlagReranker
# for cross-encoder reranking). Models are loaded lazily inside `load()` so that importing this
# module never triggers the heavy torch/FlagEmbedding import chain. Called exclusively from the
# FastAPI lifespan — routes access it through CONTEXT.
#
# Device handling: load() calls DeviceResolver.resolve() to translate the BGE_DEVICE policy
# ("auto"|"cuda"|"cpu") into a concrete device string and gated fp16 flag. Both models receive
# the resolved device via the `devices=` parameter that FlagEmbedding accepts.
#
# Revision pinning: load() calls ModelRevisionResolver.resolve() per model to turn an optional
# commit sha into a local snapshot path, which is passed as `model_name_or_path` instead of the
# bare repo id — see revision.py for why (BGEM3FlagModel/FlagReranker silently drop `revision=`).

# ====== Standard Library Imports ======
from __future__ import annotations

import math
import time
from typing import TYPE_CHECKING, Any

# ====== Third-Party Library Imports ======
from loggerplusplus import LoggerClass

# ====== Local Project Imports ======
from .cpu_budget import CpuBudgetResolver
from .device import DeviceResolver
from .revision import ModelRevisionResolver

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
        embed_revision: str | None = None,
        rerank_revision: str | None = None,
    ) -> None:
        """
        Args:
            embed_model_id (str): HuggingFace model ID for BGEM3FlagModel (dense + sparse).
            rerank_model_id (str): HuggingFace model ID for FlagReranker (cross-encoder).
            device_policy (str): BGE_DEVICE policy — "auto", "cuda", or "cpu".
            fp16_requested (bool): BGE_FP16 from config. Gated: only applied on CUDA devices.
            torch_num_threads (int): Intra-op thread cap for torch (BGE_TORCH_NUM_THREADS).
                0 means "auto" — derived inside load() as ceil(cpu_budget / 1) since the
                batching engine serialises model calls via a single asyncio.Lock (the engine
                is the concurrency gate now; the service no longer needs a concurrency hint).
                cpu_budget comes from CpuBudgetResolver — the cgroup v2 CFS quota when the
                process runs under one, else the scheduler affinity/cpu_count fallback.
                Stored here; applied at the start of load() before any torch model call.
            embed_revision (str | None): BGE_M3_REVISION — commit sha to pin the embed model
                to, or empty/None to keep the floating `main` behavior. Resolved to a local
                snapshot path by ModelRevisionResolver at the start of load().
            rerank_revision (str | None): BGE_RERANKER_REVISION — same as embed_revision, for
                the reranker.
        """
        LoggerClass.__init__(self)
        self._embed_model_id = embed_model_id
        self._rerank_model_id = rerank_model_id
        self._device_policy = device_policy
        self._fp16_requested = fp16_requested
        self._torch_num_threads = torch_num_threads
        self._embed_revision = embed_revision
        self._rerank_revision = rerank_revision
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
          3. Cap torch intra-op threads via CpuBudgetResolver (cgroup-aware).
          4. Resolve each model id to a pinned local snapshot path via ModelRevisionResolver
             (no-op, returns the bare id unchanged, when no revision is configured).
          5. Construct BGEM3FlagModel with the resolved device, fp16 flag, and path.
          6. Construct FlagReranker with the same device/fp16 flag and its resolved path.

        Raises:
            RuntimeError: When device_policy="cuda" but CUDA is not available.
            Exception: Whatever huggingface_hub.snapshot_download raises (e.g. a network
                error) when a revision is pinned but the snapshot cannot be fetched — a
                pinned deploy that cannot get its pinned weights must fail loudly, not fall
                back to the floating revision.
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
        import torch  # noqa: PLC0415
        from FlagEmbedding import BGEM3FlagModel, FlagReranker  # noqa: PLC0415

        # 3. Cap torch intra-op threads to prevent CPU oversubscription.
        # The batching engine's model_lock serialises model calls (one at a time), so the single
        # in-flight call may use all cores (_max_concurrency is 1 → no division). The explicit
        # BGE_TORCH_NUM_THREADS override exists for hosts that want a tighter cap (e.g. shared CPU).
        # Only relevant on CPU; on CUDA this has no meaningful effect but is harmless.
        # Auto-derivation (BGE_TORCH_NUM_THREADS=0) uses the cgroup v2 CFS quota when the process
        # is running under one — os.cpu_count() reports the HOST's cores, not the container's
        # limit, and setting threads off the host count oversubscribes the real allotment.
        if self._torch_num_threads > 0:
            # Explicit override from BGE_TORCH_NUM_THREADS — always wins over auto-derivation.
            n_threads = self._torch_num_threads
            budget_source = "explicit override"
            cpu_budget = self._torch_num_threads
        else:
            resolved_budget = CpuBudgetResolver.resolve()
            n_threads = max(1, math.ceil(resolved_budget.cpu_budget / max(1, self._max_concurrency)))
            budget_source = resolved_budget.source
            cpu_budget = resolved_budget.cpu_budget
        torch.set_num_threads(n_threads)
        self.logger.info(
            f"torch intra-op threads set to {n_threads} "
            f"(BGE_TORCH_NUM_THREADS={self._torch_num_threads}, "
            f"max_concurrency={self._max_concurrency}, "
            f"cpu_budget={cpu_budget}, source={budget_source})"
        )

        # 4. Resolve each model id to a pinned local snapshot path when a revision is configured.
        # No-op (returns the bare model id unchanged) when the revision env var is empty/unset —
        # preserves the floating `main` behavior for anyone who clears it. Deliberately NOT
        # wrapped in try/except: a pinned deploy that can't fetch its pinned weights must fail
        # loudly at startup, not silently fall back to floating.
        embed_source = ModelRevisionResolver.resolve(self._embed_model_id, self._embed_revision)
        rerank_source = ModelRevisionResolver.resolve(self._rerank_model_id, self._rerank_revision)

        # 5. Load the embedding model (dense + sparse heads both available from one instance).
        # The `devices` parameter accepts a device string ("cuda" / "cpu") or list thereof.
        # `embed_source` is either the bare repo id (floating) or a local snapshot dir (pinned).
        self.logger.info(
            f"Loading embed model: {self._embed_model_id} "
            f"(revision={self._embed_revision or 'main'}, source={embed_source}, "
            f"device={resolved.device}, fp16={resolved.use_fp16})"
        )
        self._embed_model = BGEM3FlagModel(
            embed_source,
            use_fp16=resolved.use_fp16,
            devices=resolved.device,
        )
        self.logger.info(f"Embed model loaded -> {self._embed_model_id} (source={embed_source})")

        # 6. Load the cross-encoder reranker with the same device settings.
        self.logger.info(
            f"Loading reranker: {self._rerank_model_id} "
            f"(revision={self._rerank_revision or 'main'}, source={rerank_source}, "
            f"device={resolved.device}, fp16={resolved.use_fp16})"
        )
        self._reranker = FlagReranker(
            rerank_source,
            use_fp16=resolved.use_fp16,
            devices=resolved.device,
        )
        self.logger.info(f"Reranker loaded -> {self._rerank_model_id} (source={rerank_source})")

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

    def encode_colbert(self, texts: list[str], max_length: int) -> list[list[list[float]]]:
        """
        Encode a batch of texts into BGE-M3's native ColBERT multi-vector representation.

        Not part of the TEI contract — an internal DocForge convention. Reuses the same
        loaded ``embed_model`` instance as ``encode_dense``/``encode_sparse`` (one shared
        forward pass internally computes dense/sparse/colbert heads together; requesting
        colbert alone here still costs its own forward pass since this call only asks for
        the colbert head).

        Args:
            texts (list[str]): Texts to embed. Must be non-empty.
            max_length (int): Maximum token length for truncation.

        Returns:
            list[list[list[float]]]: Per input text, a list of per-token 1024-dim
                L2-normalized float vectors. Token count varies per text
                (= attention_mask.sum() - 1, i.e. real tokens minus the CLS row).
        """
        device = self._resolved_device or "unknown"
        n = len(texts)
        self.logger.debug(f"encode_colbert: {n} texts, max_length={max_length}, device={device}")

        # 1. Run encode requesting only the colbert head; time the model call itself
        t0 = time.perf_counter()
        out = self.embed_model.encode(
            texts,
            return_dense=False,
            return_sparse=False,
            return_colbert_vecs=True,
            max_length=max_length,
        )
        elapsed = time.perf_counter() - t0

        # 2. Convert per-text numpy arrays ([n_tokens x 1024]) to nested Python lists
        result = [vecs.tolist() for vecs in out["colbert_vecs"]]
        self.logger.debug(
            f"encode_colbert: {n} texts -> {len(result)} token-vector-lists in {elapsed:.3f}s "
            f"(device={device})"
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
