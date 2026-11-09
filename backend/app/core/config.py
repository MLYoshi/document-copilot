from functools import lru_cache

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str
    supabase_url: str
    supabase_anon_key: str
    supabase_service_role_key: str | None = None

    openrouter_api_key: str | None = None
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    embedding_model: str = "baai/bge-m3"
    embedding_dimensions: int = 1024

    chat_model: str = "minimax/minimax-m3:free"
    summary_model: str | None = None  # 默认回退到 chat_model
    summary_max_input_chars: int = 60000

    langfuse_public_key: str | None = None
    langfuse_secret_key: str | None = None
    langfuse_host: str = "https://cloud.langfuse.com"
    retrieval_top_k: int = 8

    allowed_origins: str = "http://localhost:5173"

    corpus_owner_email: str = "corpus@system.local"

    @field_validator("database_url", "supabase_url", "supabase_anon_key")
    @classmethod
    def _not_empty(cls, value: str, info) -> str:
        if not value.strip():
            raise ValueError(f"{info.field_name} must not be empty")
        return value

    @field_validator("retrieval_top_k", "summary_max_input_chars")
    @classmethod
    def _positive_top_k(cls, value: int) -> int:
        if value < 1:
            raise ValueError("retrieval parameters must be >= 1")
        return value

    def require_openrouter_api_key(self) -> str:
        if not self.openrouter_api_key:
            raise RuntimeError("OPENROUTER_API_KEY is required for OpenRouter calls")
        return self.openrouter_api_key

    @property
    def allowed_origin_list(self) -> list[str]:
        return [
            origin.strip()
            for origin in self.allowed_origins.split(",")
            if origin.strip()
        ]


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
