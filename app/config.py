"""Application settings, loaded from environment variables (and a local .env in development).

Secrets are typed as ``SecretStr`` so they never appear in logs or reprs.
"""

from functools import lru_cache

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration. Every value has a safe default so the app boots without setup."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    gemini_api_key: SecretStr | None = None
    gemini_model: str = "gemini-3.8-flash"
    gemini_thinking_level: str = ""
    ai_timeout_seconds: float = Field(default=20.0, gt=0, le=120)
    ai_max_output_tokens: int = Field(default=2048, ge=128, le=8192)
    ai_cache_size: int = Field(default=256, ge=0)
    ai_cache_ttl_seconds: int = Field(default=3600, ge=0)

    rate_limit_per_minute: int = Field(default=30, ge=1)
    trust_proxy_headers: bool = True  # Cloud Run sits behind Google's front end

    max_text_chars: int = Field(default=4000, ge=100)
    max_image_bytes: int = Field(default=4_000_000, ge=10_000)

    @property
    def ai_enabled(self) -> bool:
        """True when a Gemini key is configured."""
        return bool(self.gemini_api_key and self.gemini_api_key.get_secret_value().strip())


@lru_cache
def get_settings() -> Settings:
    """Return the process-wide settings instance."""
    return Settings()
