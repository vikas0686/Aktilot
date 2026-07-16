from services.llm.base import (
    ChatProvider,
    EmbeddingProvider,
    ProviderNotAvailableError,
)
from services.llm.openai_provider import OpenAIChatProvider, OpenAIEmbeddingProvider
from config import settings


def get_chat_provider(provider: str | None = None) -> ChatProvider:
    name = provider or settings.llm_provider

    if name == "openai":
        if not settings.openai_api_key:
            raise ProviderNotAvailableError("OPENAI_API_KEY is not set")
        return OpenAIChatProvider(api_key=settings.openai_api_key)

    raise ProviderNotAvailableError(f"Unknown chat provider: {name}")


def get_embedding_provider(provider: str | None = None) -> EmbeddingProvider:
    name = provider or settings.embedding_provider

    if name == "openai":
        if not settings.openai_api_key:
            raise ProviderNotAvailableError("OPENAI_API_KEY is not set")
        return OpenAIEmbeddingProvider(api_key=settings.openai_api_key)

    raise ProviderNotAvailableError(f"Unknown embedding provider: {name}")
