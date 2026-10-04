"""Tests for LLM client abstraction."""

import pytest
import json
from pathlib import Path
from tracepaper.llm.client import ChatResponse, ToolCall, CachedLLMClient
from tracepaper.llm.cache import DatabaseCachedLLMClient


class MockClient:
    """Mock LLM client for testing."""

    def __init__(self, response_text="test response"):
        self.response_text = response_text
        self.call_count = 0

    def chat(self, messages, tools=None, json_schema=None):
        self.call_count += 1
        return ChatResponse(
            text=self.response_text,
            tool_calls=None,
            usage={"input_tokens": 100, "output_tokens": 50},
        )


def test_chat_response_creation():
    """Test ChatResponse dataclass creation."""
    response = ChatResponse(
        text="Hello",
        tool_calls=[ToolCall(name="test", arguments={"arg": "value"})],
        usage={"input_tokens": 10, "output_tokens": 5},
    )

    assert response.text == "Hello"
    assert len(response.tool_calls) == 1
    assert response.tool_calls[0].name == "test"
    assert response.usage["input_tokens"] == 10


def test_cached_client_caches_responses(tmp_path):
    """Test that CachedLLMClient caches responses."""
    mock = MockClient(response_text="cached response")
    cache_dir = tmp_path / ".cache"
    cache_dir.mkdir()

    cached = CachedLLMClient(mock, cache_dir=str(cache_dir), cache_enabled=True)

    messages = [{"role": "user", "content": "test"}]

    # First call should hit the mock
    response1 = cached.chat(messages)
    assert response1.text == "cached response"
    assert mock.call_count == 1

    # Second call should use cache (mock not called again)
    response2 = cached.chat(messages)
    assert response2.text == "cached response"
    assert mock.call_count == 1  # Still 1, cache was used

    # Verify cache file exists
    cache_files = list(cache_dir.glob("*.json"))
    assert len(cache_files) == 1


def test_cached_client_cache_disabled(tmp_path):
    """Test that cache can be disabled."""
    mock = MockClient(response_text="test")
    cache_dir = tmp_path / ".cache"

    cached = CachedLLMClient(mock, cache_dir=str(cache_dir), cache_enabled=False)

    messages = [{"role": "user", "content": "test"}]

    # First call
    response1 = cached.chat(messages)
    assert mock.call_count == 1

    # Second call should also hit mock (no cache)
    response2 = cached.chat(messages)
    assert mock.call_count == 2


def test_tool_call_creation():
    """Test ToolCall dataclass creation."""
    tool_call = ToolCall(name="search", arguments={"query": "test"})

    assert tool_call.name == "search"
    assert tool_call.arguments["query"] == "test"


def test_database_cached_client_persists_mock_response():
    mock = MockClient(response_text="postgres-backed cache")
    cached = DatabaseCachedLLMClient(mock, "sqlite:///:memory:")
    messages = [{"role": "user", "content": "invoice analysis"}]

    first = cached.chat(messages)
    second = cached.chat(messages)

    assert first.text == second.text == "postgres-backed cache"
    assert mock.call_count == 1
