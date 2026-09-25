from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str = (
        "postgresql+psycopg://rag:change-me-local-only@localhost:5432/rag_studio"
    )
    openrouter_api_key: SecretStr = SecretStr("")
    evaluator_model: str = ""
    evaluator_max_tokens: int = Field(default=4096, ge=512, le=8192)
    dataset_max_rows: int = Field(default=200, ge=1, le=1000)
    dataset_max_bytes: int = Field(
        default=2 * 1024 * 1024, ge=1024, le=10 * 1024 * 1024
    )
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
    cors_origins: list[str] = ["http://localhost:5273", "http://127.0.0.1:5273"]
    source_connections_enabled: bool = False
    source_connection_active_key: str = ""
    source_connection_keys: dict[str, SecretStr] = Field(default_factory=dict)
    source_connection_limit_per_project: int = Field(default=50, ge=1, le=500)
    artifact_encryption_enabled: bool = False
    artifact_encryption_mode: Literal["local-keyring", "kms", "vault"] = "local-keyring"
    artifact_active_key: str = ""
    artifact_keys: dict[str, SecretStr] = Field(default_factory=dict)
    artifact_key_references: dict[str, str] = Field(default_factory=dict)
    artifact_kms_region: str = ""
    artifact_kms_endpoint_url: str = ""
    artifact_vault_address: str = ""
    artifact_vault_token: SecretStr = SecretStr("")
    artifact_vault_mount: str = "transit"
    artifact_retention_days: int = Field(default=30, ge=1, le=3650)
    auth_mode: Literal["local", "oidc"] = "local"
    auth_oidc_issuer: str = ""
    auth_oidc_audience: str = ""
    auth_oidc_jwks_url: str = ""
    auth_oidc_algorithms: list[Literal["RS256", "RS384", "RS512", "ES256"]] = ["RS256"]
    auth_local_subject: str = "local-owner"
    auth_local_email: str = "local-owner@localhost.invalid"
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
