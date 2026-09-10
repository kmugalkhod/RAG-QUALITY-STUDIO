from pathlib import Path
from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str = (
        "postgresql+psycopg://rag:change-me-local-only@localhost:5432/rag_studio"
    )
    openrouter_api_key: SecretStr = SecretStr("")
    chat_model: str = ""
    chat_models: list[str] = []
    chat_context_tokens: int = Field(default=8192, ge=2048, le=2000000)
    chat_max_tokens: int = Field(default=1024, ge=128, le=8192)
    embedding_provider: str = "openrouter"
    embedding_model: str = "openai/text-embedding-3-small"
    embedding_dimensions: int = Field(default=1536, ge=1, le=16000)
    embedding_base_url: str = "https://openrouter.ai/api/v1"
    embedding_requests_per_minute: int = Field(default=60, ge=1, le=1000)
    embedding_revision: str = "1"
    storage_path: Path = Path("/data/documents")
    max_upload_bytes: int = Field(default=20 * 1024 * 1024, gt=0, le=100 * 1024 * 1024)
    redis_url: str = "redis://redis:6379/0"
    cors_origins: list[str] = ["http://localhost:5173", "http://127.0.0.1:5173"]
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
