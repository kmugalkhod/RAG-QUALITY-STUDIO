from pathlib import Path
from decimal import Decimal
from typing import Literal

from pydantic import Field, SecretStr, model_validator
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
    auth_mode: Literal["local", "oidc", "clerk"] = "local"
    clerk_issuer: str = ""
    clerk_jwks_url: str = ""
    clerk_secret_key: SecretStr = SecretStr("")
    clerk_authorized_origins: list[str] = [
        "http://127.0.0.1:5273",
        "http://localhost:5273",
    ]
    auth_oidc_issuer: str = ""
    auth_oidc_audience: str = ""
    auth_oidc_jwks_url: str = ""
    auth_oidc_algorithms: list[Literal["RS256", "RS384", "RS512", "ES256"]] = ["RS256"]
    auth_local_subject: str = "local-owner"
    auth_local_email: str = "local-owner@localhost.invalid"
    deployed_answers_enabled: bool = False
    deployment_local_keys_enabled: bool = False
    deployment_active_pepper: str = ""
    deployment_key_peppers: dict[str, SecretStr] = Field(default_factory=dict)
    deployment_key_rotation_grace_minutes: int = Field(default=15, ge=0, le=60)
    deployment_pricing_version: str = ""
    deployment_approved_prices: dict[str, dict[str, Decimal]] = Field(
        default_factory=dict
    )
    deployment_key_rpm: int = Field(default=10, ge=1)
    deployment_rpm: int = Field(default=30, ge=1)
    deployment_org_rpm: int = Field(default=100, ge=1)
    deployment_concurrency: int = Field(default=2, ge=1)
    deployment_org_concurrency: int = Field(default=10, ge=1)
    deployment_queue_cap: int = Field(default=20, ge=1)
    deployment_org_queue_cap: int = Field(default=100, ge=1)
    deployment_global_queue_cap: int = Field(default=1000, ge=1)
    deployment_org_daily_usd: Decimal = Field(default=Decimal("5.00"), gt=0)
    deployment_org_monthly_usd: Decimal = Field(default=Decimal("20.00"), gt=0)
    deployment_max_reserved_usd_per_run: Decimal = Field(default=Decimal("0.25"), gt=0)
    widget_enabled: bool = False
    widget_frame_origin: str = "http://127.0.0.1:5274"
    widget_token_hash_key: SecretStr = SecretStr("")
    widget_visitor_rpm: int = Field(default=5, ge=1, le=100)
    widget_exchange_rpm: int = Field(default=20, ge=1, le=1000)
    deployment_result_retention_days: int = Field(default=30, ge=1, le=365)

    @model_validator(mode="after")
    def deployment_settings_coherent(self):
        if not (
            self.deployment_key_rpm <= self.deployment_rpm <= self.deployment_org_rpm
            and self.deployment_concurrency <= self.deployment_org_concurrency
            and self.deployment_queue_cap
            <= self.deployment_org_queue_cap
            <= self.deployment_global_queue_cap
            and self.deployment_org_daily_usd <= self.deployment_org_monthly_usd
        ):
            raise ValueError("Deployment limit hierarchy is invalid.")
        if self.deployed_answers_enabled and (
            not self.deployment_pricing_version
            or not self.deployment_approved_prices
            or self.deployment_active_pepper not in self.deployment_key_peppers
            or len(
                self.deployment_key_peppers[self.deployment_active_pepper]
                .get_secret_value()
                .encode()
            )
            < 32
        ):
            raise ValueError(
                "Deployment pricing or key verification configuration is unavailable."
            )
        if self.widget_enabled and (
            not self.deployed_answers_enabled
            or len(self.widget_token_hash_key.get_secret_value().encode()) < 32
        ):
            raise ValueError(
                "Widget token hashing or deployed answers are unavailable."
            )
        return self

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
