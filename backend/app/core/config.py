from pathlib import Path
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str = (
        "postgresql+psycopg://rag:change-me-local-only@localhost:5432/rag_studio"
    )
    storage_path: Path = Path("/data/documents")
    max_upload_bytes: int = Field(default=20 * 1024 * 1024, gt=0, le=100 * 1024 * 1024)
    redis_url: str = "redis://redis:6379/0"
    cors_origins: list[str] = ["http://localhost:5173", "http://127.0.0.1:5173"]
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
