# ====== Code Summary ======
# OpenAICompatLLMProvider — ONE OpenAI-compatible chat-completions client for both local and
# external servers. Locality is a runtime flag: "external" (cloud OpenAI — api_key required)
# and "local" (vLLM/Ollama/llama.cpp — api_key usually "local") share the identical
# /chat/completions protocol. Replaces the former LocalLLMProvider + OpenAILLMProvider.

# ====== Standard Library Imports ======
from __future__ import annotations

# ====== Third-Party Library Imports ======
import httpx
from loggerplusplus import LoggerClass

# Default cloud endpoint used when an external config omits base_url.
_DEFAULT_EXTERNAL_BASE_URL = "https://api.openai.com/v1"


class OpenAICompatLLMProvider(LoggerClass):
    """
    LLM provider for any OpenAI ``/chat/completions`` server, local or external.

    Satisfies the ``LLMProvider`` protocol (``async generate``). The ``locality`` flag selects
    the deployment ("local" vs "external") and the auth policy (api_key required iff external).
    """

    def __init__(
        self,
        base_url: str,
        locality: str = "local",
        api_key: str = "local",
        model: str = "",
        max_tokens: int = 512,
        temperature: float = 0.0,
    ) -> None:
        """
        Initialize the OpenAI-compatible LLM provider.

        Args:
            base_url (str): Chat-completions base URL (cloud default applied for external).
            locality (str): "local" or "external" — sets the auth policy.
            api_key (str): Bearer token. Required (non-empty) when locality == "external".
            model (str): Model identifier sent in the request.
            max_tokens (int): Default maximum tokens to generate.
            temperature (float): Default sampling temperature.

        Raises:
            ValueError: When locality == "external" and api_key is empty.
        """
        LoggerClass.__init__(self)
        if locality == "external" and not api_key:
            raise ValueError("OpenAICompatLLMProvider: api_key is required when locality='external'.")
        self._base_url = (base_url or (_DEFAULT_EXTERNAL_BASE_URL if locality == "external" else "")).rstrip("/")
        self._locality = locality
        self._api_key = api_key
        self._model = model
        self._max_tokens = max_tokens
        self._temperature = temperature
        self.logger.info(f"OpenAICompatLLMProvider initialized — locality={locality} url={self._base_url} model={self._model}")

    async def generate(self, prompt: str, max_tokens: int = 512, temperature: float = 0.0) -> str:
        """
        Generate a chat completion via the OpenAI-compatible endpoint.

        Args:
            prompt (str): Input prompt.
            max_tokens (int): Max tokens (overrides the instance default when non-zero).
            temperature (float): Sampling temperature (overrides the instance default when non-zero).

        Returns:
            str: The text of choices[0].message.content.

        Raises:
            httpx.HTTPStatusError: On a non-2xx response.
        """
        # 1. Build the chat-completions request body
        payload = {
            "model": self._model,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": max_tokens or self._max_tokens,
            "temperature": temperature if temperature != 0.0 else self._temperature,
        }

        # 2. Send and parse the OpenAI-compatible response
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                f"{self._base_url}/chat/completions",
                headers={"Authorization": f"Bearer {self._api_key}", "Content-Type": "application/json"},
                json=payload,
            )
            response.raise_for_status()
        return response.json()["choices"][0]["message"]["content"]
