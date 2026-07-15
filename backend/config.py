from pathlib import Path

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    openai_api_key: str = ""
    context_dir: Path = Path("context")
    chat_model: str = "gpt-4o-mini"
    embedding_model: str = "text-embedding-3-small"
    # new infra
    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/docai"
    upload_dir: Path = Path("uploads")
    chroma_dir: Path = Path("chroma_data")
    temporal_address: str = "localhost:7233"
    # observability
    otel_endpoint: str = "http://localhost:4317"
    environment: str = "development"
    app_version: str = "0.1.0"

    model_config = {"env_file": ".env"}


settings = Settings()
settings.context_dir.mkdir(parents=True, exist_ok=True)
settings.upload_dir.mkdir(parents=True, exist_ok=True)
settings.chroma_dir.mkdir(parents=True, exist_ok=True)


def project_upload_dir(project_id: str) -> Path:
    """Return (and create) the upload directory for a given project."""
    path = settings.upload_dir / project_id
    path.mkdir(parents=True, exist_ok=True)
    return path
