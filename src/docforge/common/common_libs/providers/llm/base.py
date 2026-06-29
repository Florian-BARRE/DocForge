# ====== Code Summary ======
# LLMProvider Protocol — the shared interface for all text generation backends.
# All concrete LLM providers (local OpenAI-compat, OpenAI cloud, etc.) implement this.

# ====== Standard Library Imports ======
from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class LLMProvider(Protocol):
    """
    Shared interface for all text generation backends.

    Any class implementing this protocol can be used interchangeably as an LLM
    in QueryTransformStage (rewrite, HyDE, multi-query strategies) and in the S5b
    metagen stage (structured JSON generation).
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

    async def generate_json(
        self,
        prompt: str,
        schema: dict[str, Any],
        max_tokens: int = 512,
        temperature: float = 0.0,
    ) -> dict[str, Any]:
        """
        Generate a structured JSON object that conforms to ``schema``.

        Used by the S5b metagen stage to extract typed metadata from a chunk or
        document. Implementations must degrade gracefully: on a parse/validation
        failure that survives the bounded reask loop, they return an empty dict
        (``{}``) rather than raising — a single chunk never fails the document.

        Args:
            prompt (str): The input prompt describing the extraction task.
            schema (dict): A strict JSON-schema object (root object, all keys required,
                ``additionalProperties=false``) the response must satisfy.
            max_tokens (int): Maximum number of tokens to generate.
            temperature (float): Sampling temperature (0.0 = deterministic).

        Returns:
            dict: The parsed JSON object, or ``{}`` on final failure.
        """
        ...
