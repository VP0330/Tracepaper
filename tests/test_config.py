"""Tests for configuration module."""

import pytest
from tracepaper.config import Settings, get_settings


def test_config_defaults():
    """Test that Settings loads with defaults."""
    settings = Settings(cache_enabled=False)

    assert settings.llm_provider == "ollama"
    assert settings.llm_model == "qwen2.5:14b-instruct"
    assert settings.ollama_host == "http://localhost:11434"
    assert settings.embeddings_model == "all-MiniLM-L6-v2"
    assert settings.db_path == "tracepaper.db"
    assert settings.cache_dir == ".cache"
    assert settings.log_level == "info"
    assert settings.cache_enabled is False


def test_config_from_env(monkeypatch):
    """Test that Settings loads from environment variables."""
    monkeypatch.setenv("LLM_PROVIDER", "anthropic")
    monkeypatch.setenv("LLM_MODEL", "claude-3-5-sonnet-20241022")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")

    settings = Settings()

    assert settings.llm_provider == "anthropic"
    assert settings.llm_model == "claude-3-5-sonnet-20241022"
    assert settings.anthropic_api_key == "test-key"


def test_get_settings_cached():
    """Test that get_settings returns cached instance."""
    settings1 = get_settings()
    settings2 = get_settings()

    assert settings1 is settings2
