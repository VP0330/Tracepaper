"""LLM Client abstraction with Protocol for provider-agnostic interface."""

import json
import hashlib
import os
from typing import Protocol, Any, Literal
from dataclasses import dataclass
from pathlib import Path
from abc import ABC


@dataclass
class ToolCall:
    """Represents a tool call made by the LLM."""

    name: str
    arguments: dict[str, Any]


@dataclass
class ChatResponse:
    """Normalized response from any LLM provider."""

    text: str | None = None
    tool_calls: list[ToolCall] | None = None
    usage: dict[str, int] | None = None  # {"input_tokens": int, "output_tokens": int}


class LLMClient(Protocol):
    """Protocol for LLM clients - any provider implementation must conform to this."""

    def chat(
        self,
        messages: list[dict[str, str]],
        tools: list[dict[str, Any]] | None = None,
        json_schema: dict[str, Any] | None = None,
    ) -> ChatResponse:
        """
        Send a chat request to the LLM.

        Args:
            messages: List of message dicts with "role" and "content" keys.
            tools: Optional list of tool definitions for tool calling.
            json_schema: Optional JSON schema for structured output enforcement.

        Returns:
            Normalized ChatResponse with text, tool_calls, and usage.
        """
        ...


class CachedLLMClient(ABC):
    """Base class for cached LLM clients. Wraps any LLMClient with disk caching."""

    def __init__(
        self,
        client: LLMClient,
        cache_dir: str = ".cache",
        cache_enabled: bool = True,
    ):
        """
        Initialize cached client.

        Args:
            client: The underlying LLMClient to wrap.
            cache_dir: Directory to store cache files.
            cache_enabled: Whether to use caching (can be disabled for testing).
        """
        self.client = client
        self.cache_dir = Path(cache_dir)
        self.cache_enabled = cache_enabled

        if self.cache_enabled:
            self.cache_dir.mkdir(parents=True, exist_ok=True)

    def _get_cache_key(
        self,
        messages: list[dict[str, str]],
        tools: list[dict[str, Any]] | None = None,
        json_schema: dict[str, Any] | None = None,
    ) -> str:
        """Generate cache key from request parameters."""
        # Hash the messages to detect changes
        messages_str = json.dumps(messages, sort_keys=True)
        messages_hash = hashlib.sha256(messages_str.encode()).hexdigest()

        # Hash tools if present
        tools_hash = ""
        if tools:
            tools_str = json.dumps(tools, sort_keys=True)
            tools_hash = hashlib.sha256(tools_str.encode()).hexdigest()

        # Hash schema if present
        schema_hash = ""
        if json_schema:
            schema_str = json.dumps(json_schema, sort_keys=True)
            schema_hash = hashlib.sha256(schema_str.encode()).hexdigest()

        combined = f"{messages_hash}:{tools_hash}:{schema_hash}"
        return hashlib.sha256(combined.encode()).hexdigest()

    def _load_cache(self, cache_key: str) -> ChatResponse | None:
        """Load response from cache if it exists."""
        if not self.cache_enabled:
            return None

        cache_file = self.cache_dir / f"{cache_key}.json"
        if cache_file.exists():
            try:
                with open(cache_file, "r") as f:
                    data = json.load(f)
                    # Reconstruct ChatResponse
                    tool_calls = None
                    if data.get("tool_calls"):
                        tool_calls = [
                            ToolCall(name=tc["name"], arguments=tc["arguments"])
                            for tc in data["tool_calls"]
                        ]
                    return ChatResponse(
                        text=data.get("text"),
                        tool_calls=tool_calls,
                        usage=data.get("usage"),
                    )
            except Exception:
                # If cache is corrupted, ignore and re-fetch
                return None
        return None

    def _save_cache(self, cache_key: str, response: ChatResponse) -> None:
        """Save response to cache."""
        if not self.cache_enabled:
            return

        cache_file = self.cache_dir / f"{cache_key}.json"
        try:
            data = {
                "text": response.text,
                "tool_calls": (
                    [{"name": tc.name, "arguments": tc.arguments} for tc in response.tool_calls]
                    if response.tool_calls
                    else None
                ),
                "usage": response.usage,
            }
            with open(cache_file, "w") as f:
                json.dump(data, f, indent=2)
        except Exception:
            # Silently fail on cache write errors
            pass

    def chat(
        self,
        messages: list[dict[str, str]],
        tools: list[dict[str, Any]] | None = None,
        json_schema: dict[str, Any] | None = None,
    ) -> ChatResponse:
        """
        Chat with caching.

        Args:
            messages: List of message dicts.
            tools: Optional tool definitions.
            json_schema: Optional JSON schema.

        Returns:
            Cached or freshly fetched ChatResponse.
        """
        # Try cache first
        cache_key = self._get_cache_key(messages, tools, json_schema)
        cached = self._load_cache(cache_key)
        if cached is not None:
            return cached

        # Call underlying client
        response = self.client.chat(messages, tools, json_schema)

        # Save to cache
        self._save_cache(cache_key, response)

        return response
