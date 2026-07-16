from openai import AsyncOpenAI, AuthenticationError, RateLimitError

from services.llm.base import (
    ChatResult,
    EmbedResult,
    ProviderAuthError,
    ProviderServiceError,
)


class OpenAIChatProvider:
    def __init__(self, api_key: str):
        self._client = AsyncOpenAI(api_key=api_key)

    async def generate(
        self,
        model: str,
        messages: list[dict[str, str]],
        temperature: float = 0.2,
    ) -> ChatResult:
        try:
            resp = await self._client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=temperature,
            )
        except AuthenticationError as exc:
            raise ProviderAuthError(str(exc)) from exc
        except RateLimitError as exc:
            raise ProviderServiceError(str(exc), reason="rate_limit") from exc

        return ChatResult(
            content=resp.choices[0].message.content or "",
            prompt_tokens=resp.usage.prompt_tokens,
            completion_tokens=resp.usage.completion_tokens,
            total_tokens=resp.usage.total_tokens,
            finish_reason=resp.choices[0].finish_reason or "unknown",
        )


class OpenAIEmbeddingProvider:
    def __init__(self, api_key: str):
        self._client = AsyncOpenAI(api_key=api_key)

    async def embed(
        self,
        model: str,
        texts: list[str],
    ) -> EmbedResult:
        try:
            resp = await self._client.embeddings.create(
                model=model,
                input=texts,
            )
        except AuthenticationError as exc:
            raise ProviderAuthError(str(exc)) from exc
        except RateLimitError as exc:
            raise ProviderServiceError(str(exc), reason="rate_limit") from exc

        return EmbedResult(
            embeddings=[item.embedding for item in resp.data],
            total_tokens=resp.usage.total_tokens if resp.usage else 0,
        )
