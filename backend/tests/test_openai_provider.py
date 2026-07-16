"""
Tests for OpenAI provider implementations (chat + embedding).
"""

import pytest
from unittest.mock import AsyncMock, MagicMock

from services.llm.base import (
    ChatResult,
    EmbedResult,
    ProviderAuthError,
    ProviderServiceError,
)
from services.llm.openai_provider import OpenAIChatProvider, OpenAIEmbeddingProvider


def mocked_chat_response(content="Hello world", prompt_tokens=10, completion_tokens=5, finish_reason="stop"):
    response = MagicMock()
    response.choices = [MagicMock()]
    response.choices[0].message.content = content
    response.choices[0].finish_reason = finish_reason
    response.usage.prompt_tokens = prompt_tokens
    response.usage.completion_tokens = completion_tokens
    response.usage.total_tokens = prompt_tokens + completion_tokens
    return response

class TestOpenAIChatProvider:
    @pytest.mark.asyncio
    async def test_generate_returns_chat_result(self):
        provider = OpenAIChatProvider(api_key="test-key")
        provider._client.chat.completions.create = AsyncMock(
            return_value=mocked_chat_response()
        )

        result = await provider.generate(
            model="gpt-4o-mini",
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
        provider = OpenAIChatProvider(api_key="test-key")
        provider._client.chat.completions.create = AsyncMock(
            return_value=mocked_chat_response()
        )

        await provider.generate(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": "Hi"}],
            temperature=0.2,
        )

        provider._client.chat.completions.create.assert_called_once_with(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": "Hi"}],
            temperature=0.2,
        )

    @pytest.mark.asyncio
    async def test_generate_raises_provider_auth_error_on_invalid_key(self):
        from openai import AuthenticationError

        provider = OpenAIChatProvider(api_key="bad-key")
        provider._client.chat.completions.create = AsyncMock(
            side_effect=AuthenticationError(
                message="Invalid API key",
                response=MagicMock(status_code=401),
                body=None,
            )
        )

        with pytest.raises(ProviderAuthError):
            await provider.generate(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": "Hi"}],
            )

    @pytest.mark.asyncio
    async def test_generate_raises_provider_rate_limit_error(self):
        from openai import RateLimitError

        provider = OpenAIChatProvider(api_key="test-key")
        provider._client.chat.completions.create = AsyncMock(
            side_effect=RateLimitError(
                message="Rate limit exceeded",
                response=MagicMock(status_code=429),
                body=None,
            )
        )

        with pytest.raises(ProviderServiceError):
            await provider.generate(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": "Hi"}],
            )

    @pytest.mark.asyncio
    async def test_generate_handles_empty_content(self):
        provider = OpenAIChatProvider(api_key="test-key")
        provider._client.chat.completions.create = AsyncMock(
            return_value=mocked_chat_response(content=None)
        )

        result = await provider.generate(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": "Hi"}],
        )

        assert result.content == ""
        assert result.prompt_tokens == 10
        assert result.completion_tokens == 5
        assert result.total_tokens == 15
        assert result.finish_reason == "stop"


def mocked_embed_response(embeddings=None, total_tokens=8):
    if embeddings is None:
        embeddings = [[0.1, 0.2, 0.3]]

    response = MagicMock()
    response.data = []
    for embedding in embeddings:
        item = MagicMock()
        item.embedding = embedding
        response.data.append(item)
    response.usage.total_tokens = total_tokens
    return response

class TestOpenAIEmbeddingProvider:

    @pytest.mark.asyncio
    async def test_embed_returns_embed_result(self):
        provider = OpenAIEmbeddingProvider(api_key="test-key")

        provider._client.embeddings.create = AsyncMock(return_value=mocked_embed_response())

        result = await provider.embed(
            model="text-embedding-3-small",
            texts=["hello world"],
        )

        assert isinstance(result, EmbedResult)
        assert result.embeddings == [[0.1, 0.2, 0.3]]
        assert result.total_tokens == 8

    @pytest.mark.asyncio
    async def test_embed_passes_model_and_text(self):
        provider = OpenAIEmbeddingProvider(api_key="test-key")

        provider._client.embeddings.create = AsyncMock(return_value=mocked_embed_response())

        await provider.embed(
            model="text-embedding-3-small",
            texts=["hello world"],
        )

        provider._client.embeddings.create.assert_called_once_with(
            model="text-embedding-3-small",
            input=["hello world"],
        )

    @pytest.mark.asyncio
    async def test_embed_raises_provider_auth_error(self):
        from openai import AuthenticationError

        provider = OpenAIEmbeddingProvider(api_key="bad-key")
        provider._client.embeddings.create = AsyncMock(
            side_effect=AuthenticationError(
                message="Invalid API key",
                response=MagicMock(status_code=401),
                body=None,
            )
        )

        with pytest.raises(ProviderAuthError):
            await provider.embed(
                model="text-embedding-3-small",
                texts=["hello"],
            )

    @pytest.mark.asyncio
    async def test_embed_raises_provider_service_error(self):
        from openai import RateLimitError

        provider = OpenAIEmbeddingProvider(api_key="test-key")
        provider._client.embeddings.create = AsyncMock(
            side_effect=RateLimitError(
                message="Rate limit exceeded",
                response=MagicMock(status_code=429),
                body=None,
            )
        )

        with pytest.raises(ProviderServiceError):
            await provider.embed(
                model="text-embedding-3-small",
                texts=["hello"],
            )
