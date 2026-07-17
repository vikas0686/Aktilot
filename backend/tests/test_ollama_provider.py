"""
Tests for Ollama provider implementations (chat + embedding).
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from services.llm.base import (
    ChatResult,
    EmbedResult,
    ProviderServiceError,
)
from services.llm.ollama_provider import OllamaChatProvider, OllamaEmbeddingProvider


def mocked_chat_response(content="Hello world", prompt_eval_count=10, eval_count=5):
    response = MagicMock()
    response.message.content = content
    response.prompt_eval_count = prompt_eval_count
    response.eval_count = eval_count
    response.done_reason = "stop"
    return response


def mocked_embed_response(embeddings=None, prompt_eval_count=8):
    if embeddings is None:
        embeddings = [[0.1, 0.2, 0.3]]
    response = MagicMock()
    response.embeddings = embeddings
    response.prompt_eval_count = prompt_eval_count
    return response


class TestOllamaChatProvider:
    @pytest.mark.asyncio
    async def test_generate_returns_chat_result(self):
        provider = OllamaChatProvider(base_url="http://localhost:11434")
        provider._client.chat = AsyncMock(return_value=mocked_chat_response())

        result = await provider.generate(
            model="llama3.1",
            messages=[{"role": "user", "content": "Hi"}],
            temperature=0.2,
        )

        assert isinstance(result, ChatResult)
        assert result.content == "Hello world"
        assert result.prompt_tokens == 10
        assert result.completion_tokens == 5
        assert result.total_tokens == 15
        assert result.finish_reason == "stop"

    @pytest.mark.asyncio
    async def test_generate_passes_model_and_temperature(self):
        provider = OllamaChatProvider(base_url="http://localhost:11434")
        provider._client.chat = AsyncMock(return_value=mocked_chat_response())

        await provider.generate(
            model="llama3.1",
            messages=[{"role": "user", "content": "Hi"}],
            temperature=0.7,
        )

        provider._client.chat.assert_called_once_with(
            model="llama3.1",
            messages=[{"role": "user", "content": "Hi"}],
            options={"temperature": 0.7},
        )

    @pytest.mark.asyncio
    async def test_generate_raises_provider_service_error_on_connection(self):
        provider = OllamaChatProvider(base_url="http://localhost:11434")
        provider._client.chat = AsyncMock(
            side_effect=ConnectionError("Failed to connect to Ollama")
        )

        with pytest.raises(ProviderServiceError) as exc:
            await provider.generate(
                model="llama3.1",
                messages=[{"role": "user", "content": "Hi"}],
            )

        assert exc.value.reason == "connection_refused"

    @pytest.mark.asyncio
    async def test_generate_handles_empty_content(self):
        provider = OllamaChatProvider(base_url="http://localhost:11434")
        provider._client.chat = AsyncMock(return_value=mocked_chat_response(content=""))

        result = await provider.generate(
            model="llama3.1",
            messages=[{"role": "user", "content": "Hi"}],
        )

        assert result.content == ""
        assert result.prompt_tokens == 10
        assert result.completion_tokens == 5
        assert result.total_tokens == 15
        assert result.finish_reason == "stop"


class TestOllamaEmbeddingProvider:
    @pytest.mark.asyncio
    async def test_embed_returns_embed_result(self):
        provider = OllamaEmbeddingProvider(base_url="http://localhost:11434")
        provider._client.embed = AsyncMock(return_value=mocked_embed_response())

        result = await provider.embed(
            model="nomic-embed-text",
            texts=["hello world"],
        )

        assert isinstance(result, EmbedResult)
        assert result.embeddings == [[0.1, 0.2, 0.3]]
        assert result.total_tokens == 8

    @pytest.mark.asyncio
    async def test_embed_passes_model_and_input(self):
        provider = OllamaEmbeddingProvider(base_url="http://localhost:11434")
        provider._client.embed = AsyncMock(return_value=mocked_embed_response())

        await provider.embed(
            model="nomic-embed-text",
            texts=["hello world"],
        )

        provider._client.embed.assert_called_once_with(
            model="nomic-embed-text",
            input=["hello world"],
        )

    @pytest.mark.asyncio
    async def test_embed_raises_provider_service_error_on_connection(self):
        provider = OllamaEmbeddingProvider(base_url="http://localhost:11434")
        provider._client.embed = AsyncMock(
            side_effect=ConnectionError("Failed to connect to Ollama")
        )

        with pytest.raises(ProviderServiceError) as exc:
            await provider.embed(
                model="nomic-embed-text",
                texts=["hello"],
            )

        assert exc.value.reason == "connection_refused"
