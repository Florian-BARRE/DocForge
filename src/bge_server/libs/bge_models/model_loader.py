# ====== Code Summary ======
# BgeModelLoader: loads the two BGE model instances (BGEM3FlagModel for dense+sparse+colbert
# embedding and FlagReranker for cross-encoder reranking) and returns them as a LoadedModels
# record. Models are loaded lazily inside `load()` so that importing this module never triggers
# the heavy torch/FlagEmbedding import chain.
#
# Device handling: load() calls DeviceResolver.resolve() to translate the BGE_DEVICE policy
# ("auto"|"cuda"|"cpu") into a concrete device string and gated fp16 flag. Both models receive
# the resolved device via the `devices=` parameter that FlagEmbedding accepts.
#
# Revision pinning: load() calls ModelRevisionResolver.resolve() per model to turn an optional
# commit sha into a local snapshot path, which is passed as `model_name_or_path` instead of the
# bare repo id -- see revision.py for why (BGEM3FlagModel/FlagReranker silently drop `revision=`).

# ====== Standard Library Imports ======
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

# ====== Third-Party Library Imports ======
from loggerplusplus import LoggerClass

# ====== Local Project Imports ======
from .cpu_budget import CpuBudgetResolver
from .device import DeviceResolver, ResolvedDevice
from .revision import ModelRevisionResolver


@dataclass(frozen=True, slots=True)
class LoadedModels:
    """
    Outcome of BgeModelLoader.load().

    Attributes:
        embed_model (Any): The BGEM3FlagModel instance.
        reranker (Any | None): The FlagReranker instance, None when BGE_LOAD_RERANKER=false.
        device (str): Concrete device the models run on ("cuda" or "cpu").
        use_fp16 (bool): The GATED fp16 flag actually applied to the models.
        max_concurrency (int): Effective cap on simultaneous forward passes.
    """

    embed_model: Any
    reranker: Any | None
    device: str
    use_fp16: bool
    max_concurrency: int


class BgeModelLoader(LoggerClass):
    """
    Resolves device, concurrency, torch threads and model sources, then builds the models.

    The heavy FlagEmbedding / torch import is deferred to `load()` so the module itself stays
    cheap to import for testing and tooling.
    """

    def __init__(
        self,
        embed_model_id: str,
        rerank_model_id: str,
        device_policy: str,
        fp16_requested: bool,
        torch_num_threads: int,
        embed_revision: str | None,
        rerank_revision: str | None,
        load_reranker: bool,
        max_concurrent: int,
        initial_max_concurrency: int,
    ) -> None:
        """
        Args:
            embed_model_id (str): HuggingFace model ID for BGEM3FlagModel.
            rerank_model_id (str): HuggingFace model ID for FlagReranker.
            device_policy (str): BGE_DEVICE policy -- "auto", "cuda", or "cpu".
            fp16_requested (bool): BGE_FP16 from config. Gated: only applied on CUDA devices.
            torch_num_threads (int): BGE_TORCH_NUM_THREADS override (0 = derive from the cpu
                budget divided by the effective concurrency).
            embed_revision (str | None): BGE_M3_REVISION commit sha, or empty/None for `main`.
            rerank_revision (str | None): BGE_RERANKER_REVISION, same for the reranker.
            load_reranker (bool): BGE_LOAD_RERANKER. False skips constructing (and downloading)
                the FlagReranker entirely.
            max_concurrent (int): BGE_MAX_CONCURRENT -- 0 = auto (1 on CPU, else one per loaded
                model); otherwise capped at the number of loaded models.
            initial_max_concurrency (int): Concurrency assumed before load() has resolved the
                device (returned unchanged only if nothing overrides it).
        """
        LoggerClass.__init__(self)
        self._embed_model_id = embed_model_id
        self._rerank_model_id = rerank_model_id
        self._device_policy = device_policy
        self._fp16_requested = fp16_requested
        self._torch_num_threads = torch_num_threads
        self._embed_revision = embed_revision
        self._rerank_revision = rerank_revision
        self._load_reranker = load_reranker
        self._max_concurrent_cfg = max_concurrent
        self._max_concurrency = initial_max_concurrency

    def load(self) -> LoadedModels:
        """
        Resolve the device, then load the BGE embed model (and, unless gated off, the reranker).

        Steps:
          1. Call DeviceResolver.resolve() to translate the BGE_DEVICE policy into a concrete
             device string and gated fp16 flag (torch.cuda.is_available() is called here).
          2. Import FlagEmbedding (deferred -- avoids ML stack at module import time) and resolve
             the effective forward-pass concurrency.
          3. Cap torch intra-op threads via CpuBudgetResolver (cgroup-aware).
          4. Resolve the embed model id to a pinned local snapshot path via
             ModelRevisionResolver (no-op, returns the bare id unchanged, when no revision is
             configured).
          5. Construct BGEM3FlagModel with the resolved device, fp16 flag, and path.
          6. Construct FlagReranker with the same device/fp16 flag and its own resolved path --
             SKIPPED entirely when ``load_reranker=False`` (BGE_LOAD_RERANKER=false): no
             revision resolution, no download, no resident RAM for an unused model.

        Returns:
            LoadedModels: The model instances and the resolved device / fp16 / concurrency.

        Raises:
            RuntimeError: When device_policy="cuda" but CUDA is not available.
            Exception: Whatever huggingface_hub.snapshot_download raises (e.g. a network
                error) when a revision is pinned but the snapshot cannot be fetched -- a
                pinned deploy that cannot get its pinned weights must fail loudly, not fall
                back to the floating revision.
        """
        # 1. Resolve device policy -> concrete device + gated fp16
        # DeviceResolver defers the torch import inside resolve(), consistent with the
        # deferred-ML-import rule for this service.
        resolved = DeviceResolver.resolve(self._device_policy, self._fp16_requested)
        self.logger.info(
            f"Device policy '{self._device_policy}' resolved -> "
            f"device={resolved.device}, use_fp16={resolved.use_fp16}"
        )

        # 2. Defer the heavy FlagEmbedding import to this moment -- the container is booting.
        # Torch is bundled with FlagEmbedding, so import it here too, right after, to apply
        # the thread cap before any model is instantiated.
        import torch  # noqa: PLC0415
        from FlagEmbedding import BGEM3FlagModel, FlagReranker  # noqa: PLC0415

        self._resolve_max_concurrency(resolved.device)

        # 3. Cap torch intra-op threads to prevent CPU oversubscription.
        self._cap_torch_threads(torch)

        # 4-5. Resolve the embed source and load the embedding model.
        embed_model = self._build_embed_model(BGEM3FlagModel, resolved)

        # 6. Load the cross-encoder reranker (or skip it when gated off).
        reranker = self._build_reranker(FlagReranker, resolved)

        return LoadedModels(
            embed_model=embed_model,
            reranker=reranker,
            device=resolved.device,
            use_fp16=resolved.use_fp16,
            max_concurrency=self._max_concurrency,
        )

    def _resolve_max_concurrency(self, device: str) -> None:
        """
        Resolve the effective forward-pass concurrency now that the device is known.

        Args:
            device (str): The resolved device ("cuda" or "cpu").
        """
        models_count = 2 if self._load_reranker else 1
        if self._max_concurrent_cfg > 0:
            self._max_concurrency = min(models_count, self._max_concurrent_cfg)
        elif device == "cpu":
            self._max_concurrency = 1
        else:
            self._max_concurrency = models_count

    def _cap_torch_threads(self, torch: Any) -> None:
        """
        Cap torch intra-op threads to prevent CPU oversubscription.

        The batching engine holds TWO independent locks (embed_lock + rerank_lock), so up to
        two forward passes can be in flight at once (max_concurrency = 2) -- the thread budget
        is split between them so their combined usage stays within cpu_budget instead of each
        one alone claiming the full core count. The explicit BGE_TORCH_NUM_THREADS override
        exists for hosts that want a tighter (or looser) cap (e.g. shared CPU).
        Only relevant on CPU; on CUDA this has no meaningful effect but is harmless.
        Auto-derivation (BGE_TORCH_NUM_THREADS=0) uses the cgroup v2 CFS quota when the process
        is running under one -- os.cpu_count() reports the HOST's cores, not the container's
        limit, and setting threads off the host count oversubscribes the real allotment.

        Args:
            torch (Any): The imported torch module.
        """
        if self._torch_num_threads > 0:
            # Explicit override from BGE_TORCH_NUM_THREADS -- always wins over auto-derivation.
            n_threads = self._torch_num_threads
            budget_source = "explicit override"
            cpu_budget = self._torch_num_threads
        else:
            resolved_budget = CpuBudgetResolver.resolve()
            n_threads = max(
                1, math.ceil(resolved_budget.cpu_budget / max(1, self._max_concurrency))
            )
            budget_source = resolved_budget.source
            cpu_budget = resolved_budget.cpu_budget
        torch.set_num_threads(n_threads)
        self.logger.info(
            f"torch intra-op threads set to {n_threads} "
            f"(BGE_TORCH_NUM_THREADS={self._torch_num_threads}, "
            f"max_concurrency={self._max_concurrency}, "
            f"cpu_budget={cpu_budget}, source={budget_source})"
        )

    def _build_embed_model(self, model_cls: Any, resolved: ResolvedDevice) -> Any:
        """
        Resolve the embed model source and construct the BGEM3FlagModel.

        Resolves the model id to a pinned local snapshot path when a revision is configured.
        No-op (returns the bare model id unchanged) when the revision env var is empty/unset --
        preserves the floating `main` behavior for anyone who clears it. Deliberately NOT
        wrapped in try/except: a pinned deploy that can't fetch its pinned weights must fail
        loudly at startup, not silently fall back to floating.

        Args:
            model_cls (Any): The BGEM3FlagModel class.
            resolved (ResolvedDevice): Resolved device and gated fp16 flag.

        Returns:
            Any: The BGEM3FlagModel instance (dense + sparse heads from one instance).
        """
        embed_source = ModelRevisionResolver.resolve(self._embed_model_id, self._embed_revision)

        # The `devices` parameter accepts a device string ("cuda" / "cpu") or list thereof.
        # `embed_source` is either the bare repo id (floating) or a local snapshot dir (pinned).
        self.logger.info(
            f"Loading embed model: {self._embed_model_id} "
            f"(revision={self._embed_revision or 'main'}, source={embed_source}, "
            f"device={resolved.device}, fp16={resolved.use_fp16})"
        )
        embed_model = model_cls(
            embed_source,
            use_fp16=resolved.use_fp16,
            devices=resolved.device,
        )
        self.logger.info(f"Embed model loaded -> {self._embed_model_id} (source={embed_source})")
        return embed_model

    def _build_reranker(self, reranker_cls: Any, resolved: ResolvedDevice) -> Any | None:
        """
        Construct the cross-encoder reranker with the same device settings.

        SKIPPED entirely when BGE_LOAD_RERANKER=false (embed-only deployment): no download, no
        resident RAM, no 30-120s load time for a model this deployment never serves. POST
        /rerank returns a clean HTTP 503 in that case (see BgeModelsService.reranker_loaded /
        router.py). The reranker revision is only resolved when the reranker will actually be
        loaded -- resolving it needlessly would still trigger a snapshot_download (network +
        disk) for a model that is never used.

        Args:
            reranker_cls (Any): The FlagReranker class.
            resolved (ResolvedDevice): Resolved device and gated fp16 flag.

        Returns:
            Any | None: The FlagReranker instance, or None when the reranker is gated off.
        """
        if not self._load_reranker:
            self.logger.info(
                f"Reranker load SKIPPED (BGE_LOAD_RERANKER=false) -- {self._rerank_model_id} "
                f"will not be downloaded or loaded; POST /rerank will return HTTP 503"
            )
            return None

        rerank_source = ModelRevisionResolver.resolve(self._rerank_model_id, self._rerank_revision)
        self.logger.info(
            f"Loading reranker: {self._rerank_model_id} "
            f"(revision={self._rerank_revision or 'main'}, source={rerank_source}, "
            f"device={resolved.device}, fp16={resolved.use_fp16})"
        )
        reranker = reranker_cls(
            rerank_source,
            use_fp16=resolved.use_fp16,
            devices=resolved.device,
        )
        self.logger.info(f"Reranker loaded -> {self._rerank_model_id} (source={rerank_source})")
        return reranker
