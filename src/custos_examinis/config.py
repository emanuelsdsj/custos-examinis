from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "custos-examinis"
    debug: bool = False

    jwt_secret: str = "change-me-to-a-long-random-value"  # noqa: S105 - placeholder default, overridden by env
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 60

    redis_url: str = "redis://localhost:6379/0"

    anthropic_api_key: str = ""
    anthropic_model: str = "claude-sonnet-4-5"

    google_api_key: str = ""
    google_model: str = "gemini-2.5-flash"

    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "llama3.1"

    rate_limit_requests_per_minute: int = 60
    audit_rate_limit_per_hour: int = 10

    max_archive_size_bytes: int = 5 * 1024 * 1024
    max_file_count: int = 200
    max_file_size_bytes: int = 512 * 1024


@lru_cache
def get_settings() -> Settings:
    return Settings()
