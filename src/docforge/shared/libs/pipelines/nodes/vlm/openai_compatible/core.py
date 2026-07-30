# ====== Code Summary ======
# The OpenAI-compatible VLM node — the first concrete child of BaseVlmNode. Sends the image
# (base64 data URL) + the textual context through LangChain's ChatOpenAI multimodal messages;
# works against any OpenAI-compatible vision endpoint (vLLM/Qwen-VL local, OpenAI, Pixtral…).
# VLMs report no usable confidence → score 1.0 on a non-empty answer, 0.0 otherwise.

# ====== Standard Library Imports ======
import base64

# ====== Third-Party Library Imports ======
from langchain_core.messages import HumanMessage, SystemMessage

# ====== Internal Project Imports ======
from shared_libs.pipelines.nodes.openai_compat import EndpointReachability, OpenAICompatHelpers
from shared_libs.pipelines.registry import NodeRegistry

# ====== Local Project Imports ======
from ..base import BaseVlmNode
from .config import VlmOpenAICompatibleConfig


@NodeRegistry.register("vlm")
class VlmOpenAICompatibleNode(BaseVlmNode):
    """
    Describe figures through any OpenAI-compatible vision API.

    The system prompt (per figure class) drives the behaviour: photo caption, scanned-text
    complement, diagram rewriting, chart reading with optional table extraction.
    """

    KIND = "openai_compatible"
    NAME = "OpenAI-compatible VLM"
    SUMMARY = "Describe an image via any OpenAI-compatible vision endpoint."
    HOW_IT_WORKS = (
        "Sends the system prompt, the textual context (e.g. prior OCR text) and the image "
        "(base64 data URL) as a multimodal chat message and returns the model's answer."
    )
    Config = VlmOpenAICompatibleConfig

    async def preflight(self) -> None:
        """Verify the vision endpoint is reachable and its credentials accepted, before any spend."""
        config: VlmOpenAICompatibleConfig = self.config
        await EndpointReachability.check(
            node_kind=self.KIND,
            base_url=config.base_url,
            api_key=config.api_key,
            timeout_seconds=config.timeout_seconds,
        )

    async def _describe(self, image: bytes, context: str, system_prompt: str) -> tuple[str, float]:
        """Run the multimodal chat call."""
        config: VlmOpenAICompatibleConfig = self.config
        # 1. Build the multimodal message: optional context text + the image as a data URL.
        encoded = base64.b64encode(image).decode("ascii")
        content: list[dict] = []
        if context:
            content.append(
                {"type": "text", "text": f"Context extracted from the image:\n{context}"}
            )
        content.append(
            {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{encoded}"}}
        )

        # 2. Invoke the endpoint (client built by the shared factory).
        model = OpenAICompatHelpers.chat(
            config, temperature=config.temperature, max_tokens=config.max_tokens
        )
        answer = await model.ainvoke(
            [SystemMessage(content=system_prompt), HumanMessage(content=content)]
        )

        # 3. No usable confidence from a chat VLM — non-empty answer = accepted.
        text = str(answer.content)
        return text, 1.0 if text.strip() else 0.0


__all__ = ["VlmOpenAICompatibleNode"]
