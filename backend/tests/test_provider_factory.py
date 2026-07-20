"""
Tests for the provider factory.
"""

from unittest.mock import patch

import pytest

from services.llm.base import ProviderAuthError, ProviderNotAvailableError
from services.llm.ollama_provider import OllamaChatProvider, OllamaEmbeddingProvider
from services.llm.openai_provider import OpenAIChatProvider, OpenAIEmbeddingProvider


class TestProviderFactory:
    @patch("services.llm.settings.llm_provider", "openai")
    @patch("services.llm.settings.openai_api_key", "test-key")
    def test_get_chat_provider_returns_openai_by_default(self):
        from services.llm import get_chat_provider

        provider = get_chat_provider()
        assert isinstance(provider, OpenAIChatProvider)

    @patch("services.llm.settings.llm_provider", "unknown")
    def test_get_chat_provider_raises_on_unknown_provider(self):
        from services.llm import get_chat_provider

        with pytest.raises(ProviderNotAvailableError, match="Unknown chat provider"):
            get_chat_provider()

    @patch("services.llm.settings.llm_provider", "openai")
    @patch("services.llm.settings.openai_api_key", "")
    def test_get_chat_provider_raises_when_api_key_missing(self):
        from services.llm import get_chat_provider

        with pytest.raises(ProviderAuthError, match="OPENAI_API_KEY"):
            get_chat_provider()

    @patch("services.llm.settings.embedding_provider", "openai")
    @patch("services.llm.settings.openai_api_key", "test-key")
    def test_get_embedding_provider_returns_openai_by_default(self):
        from services.llm import get_embedding_provider

        provider = get_embedding_provider()
        assert isinstance(provider, OpenAIEmbeddingProvider)

    @patch("services.llm.settings.embedding_provider", "unknown")
    def test_get_embedding_provider_raises_on_unknown_provider(self):
        from services.llm import get_embedding_provider

        with pytest.raises(
            ProviderNotAvailableError, match="Unknown embedding provider"
        ):
            get_embedding_provider()

    @patch("services.llm.settings.embedding_provider", "openai")
    @patch("services.llm.settings.openai_api_key", "")
    def test_get_embedding_provider_raises_when_api_key_missing(self):
        from services.llm import get_embedding_provider

        with pytest.raises(ProviderAuthError, match="OPENAI_API_KEY"):
            get_embedding_provider()

    @patch("services.llm.settings.llm_provider", "ollama")
    @patch("services.llm.settings.ollama_base_url", "http://localhost:11434")
    def test_get_chat_provider_returns_ollama(self):
        from services.llm import get_chat_provider

        provider = get_chat_provider()
        assert isinstance(provider, OllamaChatProvider)

    @patch("services.llm.settings.embedding_provider", "ollama")
    @patch("services.llm.settings.ollama_base_url", "http://localhost:11434")
    def test_get_embedding_provider_returns_ollama(self):
        from services.llm import get_embedding_provider

        provider = get_embedding_provider()
        assert isinstance(provider, OllamaEmbeddingProvider)
