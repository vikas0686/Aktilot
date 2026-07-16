"""
Provider abstraction types for LLM and Embedding services.
"""

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class ChatResult:
    content: str
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    finish_reason: str


@dataclass(frozen=True)
class EmbedResult:
    embeddings: list[list[float]]
    total_tokens: int


class ProviderAuthError(Exception):
    pass


class ProviderServiceError(Exception):
    pass


class ProviderNotAvailableError(Exception):
    pass


class ChatProvider(Protocol):
    async def generate(
        self,
        model: str,
        messages: list[dict[str, str]],
        temperature: float = 0.2,
    ) -> ChatResult: ...


class EmbeddingProvider(Protocol):
    async def embed(
        self,
        model: str,
        texts: list[str],
    ) -> EmbedResult: ...
