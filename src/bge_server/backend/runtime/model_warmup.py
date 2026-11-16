# ====== Code Summary ======
# ModelWarmup: primes every inference path with one tiny dummy forward pass, so the first REAL
# request does not pay lazy CUDA-kernel-compile / allocator costs. Best-effort: a warmup failure
# never aborts startup, it only slows the first request.

# ====== Third-Party Library Imports ======
from loggerplusplus import LoggerClass

# ====== Internal Project Imports ======
from libs.bge_models import BgeModelsService


class ModelWarmup(LoggerClass):
    """
    Primes every inference path of the model service.

    Calls the model service DIRECTLY (not through the batching engine/HTTP) -- the engine is not
    needed to prime the model, and going through it would just add queue/lock overhead. colbert is
    primed too: it has its OWN route (/embed_colbert) and its own forward pass (the colbert head),
    so an unwarmed colbert path would leave the first late-interaction request cold. The reranker
    warmup is skipped entirely when BGE_LOAD_RERANKER=false -- there is no reranker to warm.

    Args:
        models (BgeModelsService): The loaded model service.
        max_length (int): The tokenizer max length used for the dummy embed passes.
    """

    def __init__(self, models: BgeModelsService, max_length: int) -> None:
        LoggerClass.__init__(self)
        self._models = models
        self._max_length = max_length

    def run(self) -> None:
        """Run the warmup pass; failures are logged as warnings and swallowed."""
        try:
            self._models.encode_dense(["warmup"], max_length=self._max_length)
            self._models.encode_sparse(["warmup"], max_length=self._max_length)
            # Prime the combined dense+sparse path too (its own encode() call shape) so the
            # first real /embed_all request doesn't pay lazy kernel-compile / allocator costs.
            self._models.encode_dense_sparse(["warmup"], max_length=self._max_length)
            self._models.encode_colbert(["warmup"], max_length=self._max_length)
            if self._models.reranker_loaded:
                self._models.compute_rerank_scores_flat([["warmup", "warmup"]])
            self.logger.info(f"Warmup pass completed")
        except Exception as exc:  # noqa: BLE001 — a warmup miss must never crash the lifespan
            self.logger.warning(f"Warmup pass failed (non-fatal, continuing startup): {exc}")
