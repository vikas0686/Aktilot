import httpx
from httpx import Timeout
from ollama import AsyncClient, ResponseError

from services.llm.base import ChatResult, EmbedResult, ProviderServiceError

# 120s total (LLM generation can be slow), 10s connect timeout
_DEFAULT_TIMEOUT = Timeout(timeout=120.0, connect=10.0)


class OllamaChatProvider:
    def __init__(self, base_url: str):
        self._client = AsyncClient(host=base_url, timeout=_DEFAULT_TIMEOUT)

    async def generate(
        self,
        model: str,
        messages: list[dict[str, str]],
        temperature: float = 0.2,
    ) -> ChatResult:
        try:
            resp = await self._client.chat(
                model=model,
                messages=messages,
                options={"temperature": temperature},
            )
        except (ConnectionError, httpx.ConnectError) as exc:
            raise ProviderServiceError(str(exc), reason="connection_refused") from exc
        except httpx.TimeoutException as exc:
            raise ProviderServiceError(str(exc), reason="timeout") from exc
        except ResponseError as exc:
            raise ProviderServiceError(str(exc), reason="ollama_error") from exc

        return ChatResult(
            content=resp.message.content or "",
            prompt_tokens=resp.prompt_eval_count or 0,
            completion_tokens=resp.eval_count or 0,
            total_tokens=(resp.prompt_eval_count or 0) + (resp.eval_count or 0),
            finish_reason=resp.done_reason or "stop",
        )


class OllamaEmbeddingProvider:
    def __init__(self, base_url: str):
        self._client = AsyncClient(host=base_url, timeout=_DEFAULT_TIMEOUT)

    async def embed(
        self,
        model: str,
        texts: list[str],
    ) -> EmbedResult:
        try:
            resp = await self._client.embed(
                model=model,
                input=texts,
            )
        except (ConnectionError, httpx.ConnectError) as exc:
            raise ProviderServiceError(str(exc), reason="connection_refused") from exc
        except httpx.TimeoutException as exc:
            raise ProviderServiceError(str(exc), reason="timeout") from exc
        except ResponseError as exc:
            raise ProviderServiceError(str(exc), reason="ollama_error") from exc

        return EmbedResult(
            embeddings=resp.embeddings,
            total_tokens=resp.prompt_eval_count or 0,
        )
