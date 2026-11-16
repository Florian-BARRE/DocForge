# ====== Code Summary ======
# ReadySummary: renders the structured boot summary logged once the BGE service is ready.

# ====== Third-Party Library Imports ======
from loggerplusplus import LoggerClass

# ====== Internal Project Imports ======
from config_loader import BgeServerConfig
from libs.bge_models import BgeModelsService


class ReadySummary(LoggerClass):
    """
    Logs the boot summary: models, device policy, fp16, batching knobs.

    resolved_device is set by the model service's load(); it reflects the actual device in use.
    BGE_FP16 from config is the *requested* value; models.use_fp16 is the *gated* value (forced
    false on CPU even if BGE_FP16=true was set).

    Args:
        config (type[BgeServerConfig]): The injected configuration.
        models (BgeModelsService): The loaded model service.
    """

    def __init__(self, config: type[BgeServerConfig], models: BgeModelsService) -> None:
        LoggerClass.__init__(self)
        self._config = config
        self._models = models

    def log(self, sub_batch: int) -> None:
        """
        Log the ready summary.

        Args:
            sub_batch (int): The effective sub-batch size the engine was built with.
        """
        config, models = self._config, self._models
        rerank_summary = (
            config.BGE_RERANKER_MODEL
            if models.reranker_loaded
            else "SKIPPED (BGE_LOAD_RERANKER=false)"
        )
        self.logger.info(
            f"\nBGE Server ready\n"
            f"  embed   : {config.BGE_M3_MODEL}\n"
            f"  rerank  : {rerank_summary}\n"
            f"  policy  : {config.DEVICE} -> device: {models.resolved_device or 'unknown'}\n"
            f"  fp16    : requested={config.BGE_FP16}, active={models.use_fp16}\n"
            f"  max_len : {config.BGE_M3_MAX_LENGTH}\n"
            f"  batching: max_batch={config.BGE_MAX_BATCH_SIZE}, "
            f"wait_ms={config.BGE_MAX_WAIT_MS}, "
            f"queue={config.BGE_MAX_QUEUE_SIZE}, "
            f"max_concurrent={models.max_concurrency}, sub_batch={sub_batch}, "
            f"small_lane<={config.BGE_SMALL_REQUEST_MAX_ITEMS}"
        )
