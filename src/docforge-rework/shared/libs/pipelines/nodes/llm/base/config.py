# ====== Code Summary ======
# Shared serialised config for OpenAI-style chat-completions LLM nodes. Concrete providers
# subclass this and override only what differs (endpoint default, model type, temperature range).
# The api key lives here in the config (it is part of what fully defines the node); it is not
# secured/masked.

# ====== Third-Party Library Imports ======
from pydantic import Field

# ====== Internal Project Imports ======
from shared_libs.pipelines.base import NodeConfig


class BaseLlmChatConfig(NodeConfig):
    """
    Common configuration of a chat-completions LLM endpoint.

    Attributes:
        base_url (str): Base URL of the endpoint (set per collection).
        api_key (str): API key for the endpoint.
        model (str): Model name to request.
        temperature (float): Sampling temperature.
        max_tokens (int): Maximum number of tokens to generate.
        timeout_seconds (float): Per-request timeout.
    """

    base_url: str = Field(description="Base URL of the chat-completions endpoint.")
    api_key: str = Field(description="API key for the endpoint.")
    model: str = Field(description="Model name to request.")
    temperature: float = Field(default=0.0, ge=0.0, le=2.0, description="Sampling temperature.")
    max_tokens: int = Field(default=1024, ge=1, description="Maximum tokens to generate.")
    timeout_seconds: float = Field(default=60.0, gt=0.0, description="Per-request timeout (s).")


__all__ = ["BaseLlmChatConfig"]
