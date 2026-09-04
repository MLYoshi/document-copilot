from functools import lru_cache

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Database
    database_url: str

    # JWT auth
    jwt_secret_key: str
    jwt_algorithm: str = "HS256"
    jwt_access_token_expire_minutes: int = 30
    jwt_refresh_token_expire_days: int = 30

    # OpenRouter (LLM / embeddings) — OpenAI-compatible endpoint
    openrouter_api_key: str | None = None
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    embedding_model: str = "nvidia/nemotron-3-embed-1b:free"
    embedding_dimensions: int = 2048

    # CORS
    allowed_origins: str = "http://localhost:5173"

    # Ingest
    # Shared corpus documents are owned by this virtual system user
    corpus_owner_email: str = "corpus@system.local"

    @field_validator("database_url", "jwt_secret_key")
    @classmethod
    def _not_empty(cls, value: str, info) -> str:
        if not value.strip():
            raise ValueError(f"{info.field_name} must not be empty")
        return value

    @field_validator("jwt_secret_key")
    @classmethod
    def _sufficient_key_length(cls, value: str) -> str:
        # RFC 7518 recommends >= 32 bytes for HS256; shorter keys are rejected
        # at startup so a placeholder secret never reaches production.
        if len(value.encode()) < 32:
            raise ValueError("jwt_secret_key must be at least 32 bytes (e.g. `openssl rand -hex 32`)")
        return value

    @property
    def allowed_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.allowed_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
