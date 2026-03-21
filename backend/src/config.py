from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class DatabaseSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="SUPABASE_")

    url: str = ""
    anon_key: str = ""
    service_role_key: str = ""
    db_url: str = ""


class AnthropicSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="ANTHROPIC_")

    api_key: str = ""


class FishAudioSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="FISH_AUDIO_")

    api_key: str = ""


class FalSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="FAL_AI_")

    api_key: str = ""


class GroqSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="GROQ_")

    api_key: str = ""


class StorageSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="R2_")

    account_id: str = ""
    access_key_id: str = ""
    secret_access_key: str = ""
    bucket_name: str = "crimemill-assets"
    public_url: str = ""


class YouTubeSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="YOUTUBE_")

    client_id: str = ""
    client_secret: str = ""


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    environment: Literal["development", "staging", "production"] = "development"
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    max_concurrent_jobs: int = Field(default=3, ge=1, le=20)
    pipeline_poll_interval_seconds: int = Field(default=5, ge=1, le=60)
    healthchecks_ping_url: str = ""

    database: DatabaseSettings = Field(default_factory=DatabaseSettings)
    anthropic: AnthropicSettings = Field(default_factory=AnthropicSettings)
    fish_audio: FishAudioSettings = Field(default_factory=FishAudioSettings)
    fal: FalSettings = Field(default_factory=FalSettings)
    groq: GroqSettings = Field(default_factory=GroqSettings)
    storage: StorageSettings = Field(default_factory=StorageSettings)
    youtube: YouTubeSettings = Field(default_factory=YouTubeSettings)

    @property
    def is_production(self) -> bool:
        return self.environment == "production"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
