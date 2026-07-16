from pathlib import Path

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    openai_api_key: str = ""
    context_dir: Path = Path("context")
    llm_provider: str = "openai"
    chat_model: str = "gpt-4o-mini"
    embedding_provider: str = "openai"
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
    # public share links
    share_visitor_cookie_name: str = "aktilot_vid"
    share_visitor_hourly_message_cap: int = 20
    share_default_daily_message_cap: int = 200
    share_visitor_retention_days: int = 7
    share_retention_sweep_interval_seconds: int = 3600

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
