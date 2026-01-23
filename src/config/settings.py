from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    # DeepL API
    deepl_api_key: str
    deepl_timeout: int = 30  # seconds
    deepl_max_retries: int = 3

    # Server
    host: str = "0.0.0.0"
    port: int = 8000
    debug: bool = False

    # Authentication
    api_key: str = ""  # API key for authenticating requests
    api_key_header: str = "X-API-Key"

    # Rate limiting
    rate_limit_requests: int = 100  # requests per window
    rate_limit_window: int = 60  # window in seconds

    # Limits
    max_file_size_mb: int = 10
    max_languages_per_batch: int = 20

    # Logging
    log_level: str = "INFO"
    log_format: str = "json"  # "json" or "text"

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


@lru_cache
def get_settings() -> Settings:
    return Settings()
