# ====== Code Summary ======
# The Mistral OCR node — the ROBUST tail of an OCR escalation. POSTs the crop (base64 data URL) to
# the Mistral document-OCR API and joins the returned pages' markdown. The API reports no
# confidence → score 1.0 on non-empty text, 0.0 otherwise (as the escalation tail, nothing gates
# after it).

# ====== Standard Library Imports ======
import base64

# ====== Third-Party Library Imports ======
import httpx

# ====== Internal Project Imports ======
from shared_libs.pipelines.nodes.openai_compat import EndpointReachability
from shared_libs.pipelines.registry import NodeRegistry

# ====== Local Project Imports ======
from ..base import BaseOcrNode
from .config import OcrMistralConfig


@NodeRegistry.register("ocr")
class OcrMistralNode(BaseOcrNode):
    """Hosted robust OCR (Mistral OCR API) — the chain's safety net."""

    KIND = "mistral"
    NAME = "Mistral OCR"
    SUMMARY = "Hosted robust OCR via the Mistral document-OCR API."
    HOW_IT_WORKS = (
        "POSTs the crop as a base64 data URL to the Mistral /ocr endpoint and joins the returned "
        "pages' markdown. Typically wired as the robust tail of an OCR escalation (ScoreBelow)."
    )
    Config = OcrMistralConfig

    async def preflight(self) -> None:
        """Verify the Mistral OCR endpoint is reachable and its key accepted, before any spend."""
        config: OcrMistralConfig = self.config
        await EndpointReachability.check(
            node_kind=self.KIND,
            base_url=config.base_url,
            api_key=config.api_key,
            timeout_seconds=config.timeout_seconds,
        )

    async def _read(self, image: bytes) -> tuple[str, float]:
        """Call the OCR endpoint on one image."""
        config: OcrMistralConfig = self.config
        # 1. The API takes the image as a data URL document.
        encoded = base64.b64encode(image).decode("ascii")
        payload = {
            "model": config.model,
            "document": {
                "type": "image_url",
                "image_url": f"data:image/png;base64,{encoded}",
            },
        }

        # 2. POST and join the pages' markdown.
        async with httpx.AsyncClient(
            base_url=config.base_url, timeout=config.timeout_seconds
        ) as client:
            response = await client.post(
                "/ocr",
                json=payload,
                headers={"Authorization": f"Bearer {config.api_key}"},
            )
            response.raise_for_status()
        pages = response.json().get("pages", [])
        text = "\n\n".join(page.get("markdown", "") for page in pages).strip()

        # 3. No confidence from the API — non-empty text = accepted.
        return text, 1.0 if text else 0.0


__all__ = ["OcrMistralNode"]
