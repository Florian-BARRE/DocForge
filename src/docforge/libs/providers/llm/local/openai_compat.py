# ====== Code Summary ======
# LocalLLMProvider — local OpenAI-compatible LLM server client.
# Sends POST requests to a local /chat/completions endpoint (vLLM, Ollama,
# llama.cpp, etc.) and returns the generated text.

# ====== Standard Library Imports ======
from __future__ import annotations

# ====== Third-Party Library Imports ======
import httpx
from loggerplusplus import LoggerClass


class LocalLLMProvider(LoggerClass):
    """
    LLM provider backed by any local OpenAI-compatible chat completions endpoint.

    Targets self-hosted servers such as vLLM, Ollama, llama.cpp, or any other
    OpenAI-compatible inference server.

    Attributes:
        _base_url (str): Chat completions base URL (e.g. ``http://localhost:8080/v1``).
        _api_key (str): API key (typically ``"local"`` for unauthenticated local servers).
        _model (str): Model identifier passed to the completions endpoint.
        _max_tokens (int): Default maximum tokens to generate.
        _temperature (float): Default sampling temperature.
    """

    def __init__(
        self,
        base_url: str,
        api_key: str,
        model: str,
        max_tokens: int = 512,
        temperature: float = 0.0,
    ) -> None:
        """
        Initialize the local LLM provider.

        Args:
            base_url (str): Base URL for the OpenAI-compatible server.
            api_key (str): API key (use ``"local"`` for unauthenticated servers).
            model (str): Model identifier to pass to the completions request.
            max_tokens (int): Default maximum tokens to generate.
            temperature (float): Default sampling temperature.
        """
        LoggerClass.__init__(self)
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._model = model
        self._max_tokens = max_tokens
        self._temperature = temperature
        self.logger.info(f"LocalLLMProvider initialized — url={self._base_url} model={self._model}")

    async def generate(self, prompt: str, max_tokens: int = 512, temperature: float = 0.0) -> str:
        """
        Generate a text completion using the local OpenAI-compatible endpoint.

        Args:
            prompt (str): Input prompt to complete.
            max_tokens (int): Maximum tokens in the response (overrides instance default).
            temperature (float): Sampling temperature (overrides instance default).

        Returns:
            str: Generated text from choices[0].message.content.

        Raises:
            httpx.HTTPStatusError: If the server returns a non-2xx response.
        """
        # 1. Build the chat completions request
        payload = {
            "model": self._model,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": max_tokens or self._max_tokens,
            "temperature": temperature if temperature != 0.0 else self._temperature,
        }

        # 2. Send and parse the response
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                f"{self._base_url}/chat/completions",
                headers={
                    "Authorization": f"Bearer {self._api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
            )
            response.raise_for_status()

        # 3. Extract generated text from OpenAI-compatible response structure
        data = response.json()
        return data["choices"][0]["message"]["content"]
