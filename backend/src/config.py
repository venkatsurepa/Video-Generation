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
    endpoint_url: str = Field(
        default="",
        description="Override S3 endpoint (e.g. http://localhost:9000 for MinIO). "
        "When empty, defaults to https://{account_id}.r2.cloudflarestorage.com",
    )


class RemotionSettings(BaseSettings):
    """Remotion Lambda configuration.

    Required setup:
    1. AWS account with Lambda enabled in the target region
    2. Deploy Remotion bundle: npx remotion lambda sites create video/src/index.ts
    3. Deploy Lambda function: npx remotion lambda functions deploy
    4. Set the environment variables below
    """

    model_config = SettingsConfigDict(env_prefix="REMOTION_")

    aws_access_key_id: str = ""
    aws_secret_access_key: str = ""
    aws_region: str = "us-east-1"
    lambda_function_name: str = ""
    serve_url: str = Field(
        default="",
        description="Remotion site URL from `npx remotion lambda sites create`",
    )
    render_timeout_ms: int = Field(default=300_000, description="Lambda render timeout")
    frames_per_lambda: int = Field(default=20, description="Frames per Lambda invocation chunk")
    render_script_path: str = Field(
        default="video/scripts/render_video.ts",
        description="Path to the Node.js render bridge script relative to repo root",
    )


class BudgetSettings(BaseSettings):
    """Per-video budget enforcement settings."""

    model_config = SettingsConfigDict(env_prefix="BUDGET_")

    per_video_usd: float = Field(default=15.0, description="Hard cap per video in USD")
    soft_alert_pct: float = Field(
        default=0.70, ge=0.0, le=1.0, description="Soft alert threshold (fraction of budget)"
    )
    hard_alert_pct: float = Field(
        default=0.90, ge=0.0, le=1.0, description="Hard alert threshold — trigger degradation"
    )


class BuzzsproutSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="BUZZSPROUT_")

    podcast_id: str = ""
    api_key: str = ""


class CourtListenerSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="COURTLISTENER_")

    api_token: str = ""


class YouTubeSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="YOUTUBE_")

    client_id: str = ""
    client_secret: str = ""


class DiscordSettings(BaseSettings):
    """Discord integration — webhooks for notifications, bot token for threads."""

    model_config = SettingsConfigDict(env_prefix="DISCORD_")

    webhook_url: str = ""
    bot_token: str = ""
    guild_id: str = ""
    case_discussion_channel_id: str = ""


class PatreonSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="PATREON_")

    campaign_id: str = ""
    access_token: str = ""


class GoogleFormsSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="GOOGLE_FORMS_")

    sheet_id: str = ""


class RepurposeSettings(BaseSettings):
    """Repurpose.io — trigger-based cross-platform distribution ($35/month)."""

    model_config = SettingsConfigDict(env_prefix="REPURPOSE_IO_")

    api_key: str = ""
    workflow_id: str = ""


class AyrshareSettings(BaseSettings):
    """Ayrshare — unified social media API fallback ($49/month)."""

    model_config = SettingsConfigDict(env_prefix="AYRSHARE_")

    api_key: str = ""


class NewsletterSettings(BaseSettings):
    """Email newsletter via Resend.

    Reads RESEND_API_KEY and NEWSLETTER_FROM_EMAIL from environment.
    """

    model_config = SettingsConfigDict(env_prefix="NEWSLETTER_")

    resend_api_key: str = Field(
        default="",
        validation_alias="RESEND_API_KEY",
    )
    from_email: str = "noreply@crimemill.com"


class SelfHostingSettings(BaseSettings):
    """Self-hosted model infrastructure configuration.

    These settings are only needed when using self-hosted providers
    (chatterbox, kokoro, local_flux, ace_step).  Leave blank to use
    API-only providers.
    """

    model_config = SettingsConfigDict(env_prefix="SELF_HOSTED_")

    tts_url: str = Field(
        default="",
        description="Chatterbox/Kokoro TTS endpoint (e.g., http://gpu-host:8880)",
    )
    image_url: str = Field(
        default="",
        description="Local Flux Dev / ComfyUI endpoint (e.g., http://gpu-host:8188)",
    )
    music_url: str = Field(
        default="",
        description="ACE-Step music generation endpoint (e.g., http://gpu-host:8890)",
    )
    tts_provider: str = Field(
        default="fish_audio",
        description="TTS provider: fish_audio | chatterbox | kokoro",
    )
    image_provider: str = Field(
        default="fal_ai",
        description="Image provider: fal_ai | local_flux",
    )
    music_provider: str = Field(
        default="epidemic_sound_library",
        description="Music provider: epidemic_sound_library | ace_step",
    )
    llm_provider: str = Field(
        default="anthropic",
        description="LLM provider: anthropic",
    )


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
    cors_allowed_origins: str = Field(
        default="*",
        description="Comma-separated allowed CORS origins for production",
    )

    database: DatabaseSettings = Field(default_factory=DatabaseSettings)
    anthropic: AnthropicSettings = Field(default_factory=AnthropicSettings)
    fish_audio: FishAudioSettings = Field(default_factory=FishAudioSettings)
    fal: FalSettings = Field(default_factory=FalSettings)
    groq: GroqSettings = Field(default_factory=GroqSettings)
    storage: StorageSettings = Field(default_factory=StorageSettings)
    remotion: RemotionSettings = Field(default_factory=RemotionSettings)
    budget: BudgetSettings = Field(default_factory=BudgetSettings)
    buzzsprout: BuzzsproutSettings = Field(default_factory=BuzzsproutSettings)
    youtube: YouTubeSettings = Field(default_factory=YouTubeSettings)
    discord: DiscordSettings = Field(default_factory=DiscordSettings)
    patreon: PatreonSettings = Field(default_factory=PatreonSettings)
    google_forms: GoogleFormsSettings = Field(default_factory=GoogleFormsSettings)
    repurpose: RepurposeSettings = Field(default_factory=RepurposeSettings)
    ayrshare: AyrshareSettings = Field(default_factory=AyrshareSettings)
    newsletter: NewsletterSettings = Field(default_factory=NewsletterSettings)
    self_hosting: SelfHostingSettings = Field(default_factory=SelfHostingSettings)
    court_listener: CourtListenerSettings = Field(default_factory=CourtListenerSettings)

    @property
    def is_production(self) -> bool:
        return self.environment == "production"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
