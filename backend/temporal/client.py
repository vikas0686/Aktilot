from temporalio.client import Client

from config import settings

_client: Client | None = None


async def init_temporal_client() -> None:
    global _client
    _client = await Client.connect(settings.temporal_address)


async def get_temporal_client() -> Client:
    global _client
    if _client is None:
        _client = await Client.connect(settings.temporal_address)
    return _client


def close_temporal_client() -> None:
    global _client
    _client = None
