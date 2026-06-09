from pydantic_settings import BaseSettings
from pathlib import Path


class Settings(BaseSettings):
    openai_api_key: str = ""
    context_dir: Path = Path("context")
    chat_model: str = "gpt-4o-mini"
    embedding_model: str = "text-embedding-3-small"

    model_config = {"env_file": ".env"}


settings = Settings()
settings.context_dir.mkdir(parents=True, exist_ok=True)
