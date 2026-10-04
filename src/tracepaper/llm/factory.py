"""Construct the configured provider client for the agent loop."""

from tracepaper.config import Settings

from .anthropic import AnthropicClient
from .cache import DatabaseCachedLLMClient
from .client import LLMClient
from .ollama import OllamaClient


def create_llm_client(settings: Settings) -> LLMClient:
    """Create the configured LLM and wrap it with the disk cache."""
    if settings.llm_provider == "ollama":
        client: LLMClient = OllamaClient(
            host=settings.ollama_host,
            model=settings.llm_model,
        )
    elif settings.llm_provider == "anthropic":
        client = AnthropicClient(
            api_key=settings.anthropic_api_key,
            model=settings.llm_model,
        )
    else:
        raise ValueError(f"Unsupported LLM provider: {settings.llm_provider}")

    if settings.cache_enabled:
        return DatabaseCachedLLMClient(client, settings.database_url)
    return client
