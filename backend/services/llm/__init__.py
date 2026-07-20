from config import settings
from services.llm.base import (
    ChatProvider,
    EmbeddingProvider,
    ProviderAuthError,
    ProviderNotAvailableError,
)
from services.llm.ollama_provider import OllamaChatProvider, OllamaEmbeddingProvider
from services.llm.openai_provider import OpenAIChatProvider, OpenAIEmbeddingProvider


def get_chat_provider(provider: str | None = None) -> ChatProvider:
    name = provider or settings.llm_provider

    if name == "openai":
        if not settings.openai_api_key:
            raise ProviderAuthError("OPENAI_API_KEY is not set")
        return OpenAIChatProvider(api_key=settings.openai_api_key)

    if name == "ollama":
        return OllamaChatProvider(base_url=settings.ollama_base_url)

    raise ProviderNotAvailableError(f"Unknown chat provider: {name}")


def get_embedding_provider(provider: str | None = None) -> EmbeddingProvider:
    name = provider or settings.embedding_provider

    if name == "openai":
        if not settings.openai_api_key:
            raise ProviderAuthError("OPENAI_API_KEY is not set")
        return OpenAIEmbeddingProvider(api_key=settings.openai_api_key)

    if name == "ollama":
        return OllamaEmbeddingProvider(base_url=settings.ollama_base_url)

    raise ProviderNotAvailableError(f"Unknown embedding provider: {name}")
