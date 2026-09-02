# ====== Code Summary ======
# The PaddleOCR node — an OCR provider backed by the in-stack paddle_server sidecar's OCR-only
# endpoint (POST /ocr, raw image bytes in, {text, confidence} out). A cheap-to-mid local-network
# head or tail of an OCR escalation, interchangeable with rapidocr/mistral behind the family
# contract. Pure httpx client: zero new worker deps, no device logic (the sidecar owns cpu/gpu).
# The sidecar reports the mean recognition confidence, which is what a ScoreBelow transition
# escalates on.

# ====== Standard Library Imports ======
import httpx

# ====== Internal Project Imports ======
from shared_libs.pipelines.nodes.openai_compat import EndpointReachability
from shared_libs.pipelines.nodes.retry import NetworkRetry
from shared_libs.pipelines.registry import NodeRegistry

# ====== Local Project Imports ======
from ..base import BaseOcrNode
from .config import OcrPaddleConfig


@NodeRegistry.register("ocr")
class OcrPaddleNode(BaseOcrNode):
    """OCR via the in-stack paddle_server sidecar (PaddleOCR text detection + recognition)."""

    KIND = "paddle"
    NAME = "PaddleOCR (sidecar)"
    SUMMARY = "OCR a crop via the in-stack paddle_server sidecar (PaddleOCR text det+rec)."
    HOW_IT_WORKS = (
        "POSTs the crop's raw bytes to the paddle_server sidecar's /ocr endpoint and returns the "
        "joined recognized text scored by the sidecar's mean recognition confidence; a weak "
        "reading escalates via a ScoreBelow transition."
    )
    Config = OcrPaddleConfig

    async def preflight(self) -> None:
        """Verify the sidecar is reachable before any spend — probes its ``/health`` route."""
        config: OcrPaddleConfig = self.config
        await EndpointReachability.check(
            node_kind=self.KIND,
            base_url=config.base_url,
            api_key=config.api_key,
            timeout_seconds=config.preflight_timeout_seconds,
            path="/health",
        )

    async def _read(self, image: bytes) -> tuple[str, float]:
        """Call the sidecar's OCR endpoint on one image, with a bounded transient retry."""
        config: OcrPaddleConfig = self.config
        headers = {"Content-Type": "image/png"}
        if config.api_key:
            headers["Authorization"] = f"Bearer {config.api_key}"

        async def _post() -> tuple[str, float]:
            """POST the raw image bytes and read back {text, confidence} — the retryable call."""
            async with httpx.AsyncClient(
                base_url=config.base_url, timeout=config.timeout_seconds
            ) as client:
                response = await client.post("/ocr", content=image, headers=headers)
                response.raise_for_status()
            body = response.json()
            # Clamp to [0, 1] so a ScoreBelow gate stays well-defined even if the sidecar ever
            # reports an out-of-range confidence.
            confidence = max(0.0, min(1.0, float(body.get("confidence", 0.0))))
            return str(body.get("text", "")), confidence

        # Run under the shared bounded retry; a non-transient error re-raises at once.
        return await NetworkRetry.run(
            _post,
            max_retries=config.max_retries,
            retry_backoff_seconds=config.retry_backoff_seconds,
            label=f"ocr '{self.KIND}'",
        )


__all__ = ["OcrPaddleNode"]
