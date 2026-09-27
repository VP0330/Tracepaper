"""Pytest configuration and shared fixtures."""

import pytest
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))


@pytest.fixture
def settings():
    """Provide test settings with cache disabled."""
    from tracepaper.config import Settings

    return Settings(cache_enabled=False, db_path=":memory:")


@pytest.fixture
def mock_llm_client(settings):
    """Provide a mock LLM client for testing."""
    from tracepaper.llm.client import ChatResponse, ToolCall

    class MockLLMClient:
        def chat(self, messages, tools=None, json_schema=None):
            # Simple mock response
            return ChatResponse(
                text="Mock response",
                tool_calls=None,
                usage={"input_tokens": 10, "output_tokens": 5},
            )

    return MockLLMClient()


@pytest.fixture
def temp_cache_dir(tmp_path):
    """Provide a temporary cache directory."""
    cache_dir = tmp_path / ".cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    return cache_dir
