# ====== Code Summary ======
# OpenAILLMProvider — OpenAI cloud LLM provider.
# Sends POST requests to https://api.openai.com/v1/chat/completions and returns
# the generated text.  Shares the same interface as LocalLLMProvider.

# ====== Standard Library Imports ======
from __future__ import annotations

# ====== Third-Party Library Imports ======
import httpx
from loggerplusplus import LoggerClass

_OPENAI_BASE_URL = "https://api.openai.com/v1"


class OpenAILLMProvider(LoggerClass):
    """
    LLM provider backed by the OpenAI chat completions cloud API.

    Targets the public OpenAI API at https://api.openai.com/v1.
    api_key is mandatory — build() raises ValueError when empty.

    Attributes:
        _api_key (str): OpenAI API key.
        _model (str): OpenAI model identifier (e.g. ``gpt-4o-mini``).
        _max_tokens (int): Default maximum tokens to generate.
        _temperature (float): Default sampling temperature.
    """

    def __init__(
        self,
        api_key: str,
        model: str,
        max_tokens: int = 512,
        temperature: float = 0.0,
    ) -> None:
        """
        Initialize the OpenAI LLM provider.

        Args:
            api_key (str): OpenAI API key — must not be empty.
            model (str): OpenAI model identifier (e.g. ``gpt-4o-mini``).
            max_tokens (int): Default maximum tokens to generate.
            temperature (float): Default sampling temperature.
        """
        LoggerClass.__init__(self)
        self._api_key = api_key
        self._model = model
        self._max_tokens = max_tokens
        self._temperature = temperature
        self.logger.info(f"OpenAILLMProvider initialized — model={self._model}")

    async def generate(self, prompt: str, max_tokens: int = 512, temperature: float = 0.0) -> str:
        """
        Generate a text completion using the OpenAI chat completions API.

        Args:
            prompt (str): Input prompt to complete.
            max_tokens (int): Maximum tokens in the response (overrides instance default).
            temperature (float): Sampling temperature (overrides instance default).

        Returns:
            str: Generated text from choices[0].message.content.

        Raises:
            httpx.HTTPStatusError: If OpenAI returns a non-2xx response.
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
                f"{_OPENAI_BASE_URL}/chat/completions",
                headers={
                    "Authorization": f"Bearer {self._api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
            )
            response.raise_for_status()

        # 3. Extract generated text from the OpenAI response structure
        data = response.json()
        return data["choices"][0]["message"]["content"]
