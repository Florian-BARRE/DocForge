# ====== Code Summary ======
# LLMProvider Protocol — the shared interface for all text generation backends.
# All concrete LLM providers (local OpenAI-compat, OpenAI cloud, etc.) implement this.

# ====== Standard Library Imports ======
from typing import Protocol, runtime_checkable


@runtime_checkable
class LLMProvider(Protocol):
    """
    Shared interface for all text generation backends.

    Any class implementing this protocol can be used interchangeably as an LLM
    in QueryTransformStage (rewrite, HyDE, multi-query strategies).
    """

    async def generate(self, prompt: str, max_tokens: int = 512, temperature: float = 0.0) -> str:
        """
        Generate a text completion for the given prompt.

        Args:
            prompt (str): The input prompt.
            max_tokens (int): Maximum number of tokens to generate.
            temperature (float): Sampling temperature (0.0 = deterministic).

        Returns:
            str: Generated text completion.
        """
        ...
