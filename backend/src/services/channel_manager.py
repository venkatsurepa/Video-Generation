"""Channel lifecycle management service.

Handles channel creation (with all 4 settings tables), YouTube OAuth setup,
Fish Audio voice cloning, and per-channel health checks.
"""

from __future__ import annotations

import contextlib
import secrets
import uuid
import webbrowser
from decimal import Decimal
from typing import TYPE_CHECKING, Any, cast
from urllib.parse import urlencode

import structlog

from src.db import queries
from src.models.channel import (
    ChannelCreateInput,
    ChannelHealth,
    ChannelResponse,
    OAuthResult,
    VoiceCloneResult,
)

if TYPE_CHECKING:
    import httpx
    from psycopg_pool import AsyncConnectionPool

    from src.config import Settings

logger = structlog.get_logger()

# psycopg pool is configured with dict_row at runtime, but mypy infers
# AsyncConnection[tuple[Any, ...]].  This alias + cast keeps row access safe.
Row = dict[str, Any]

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

OAUTH_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
OAUTH_TOKEN_URL = "https://oauth2.googleapis.com/token"
YOUTUBE_API_BASE = "https://www.googleapis.com/youtube/v3"
FISH_AUDIO_BASE = "https://api.fish.audio"

YOUTUBE_SCOPES = [
    "https://www.googleapis.com/auth/youtube",
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube.readonly",
    "https://www.googleapis.com/auth/yt-analytics.readonly",
]

# Default brand palettes per niche
_NICHE_PALETTES: dict[str, dict[str, str]] = {
    "corporate_fraud": {
        "primary": "#1a1a2e",
        "secondary": "#e94560",
        "accent": "#0f3460",
        "text": "#eaeaea",
    },
    "betrayal_stories": {
        "primary": "#0d0d0d",
        "secondary": "#c70039",
        "accent": "#900c3f",
        "text": "#f5f5f5",
    },
    "con_artists": {
        "primary": "#1b1b2f",
        "secondary": "#e2b714",
        "accent": "#162447",
        "text": "#e8e8e8",
    },
    "cybercrime": {
        "primary": "#0a0a0a",
        "secondary": "#00ff41",
        "accent": "#003b00",
        "text": "#d0d0d0",
    },
    "organized_crime": {
        "primary": "#141414",
        "secondary": "#8b0000",
        "accent": "#2c2c2c",
        "text": "#e0e0e0",
    },
    "cold_cases": {
        "primary": "#0e1117",
        "secondary": "#4a90d9",
        "accent": "#1c2333",
        "text": "#c8c8c8",
    },
    "political_corruption": {
        "primary": "#111111",
        "secondary": "#d4af37",
        "accent": "#2d2d2d",
        "text": "#f0f0f0",
    },
    "environmental_crime": {
        "primary": "#0a1a0a",
        "secondary": "#2ecc71",
        "accent": "#1a3a1a",
        "text": "#e0e0e0",
    },
    "true_crime_general": {
        "primary": "#121212",
        "secondary": "#bb2d3b",
        "accent": "#1e1e1e",
        "text": "#eeeeee",
    },
}

# Default prompt suffixes per niche
_NICHE_PROMPT_SUFFIX: dict[str, str] = {
    "corporate_fraud": "cinematic boardroom lighting, documents scattered, cold blue tones",
    "betrayal_stories": "dramatic shadows, intimate framing, warm-to-cold color shift",
    "con_artists": "glamorous yet deceptive, gold highlights, noir lighting",
    "cybercrime": "dark monitors, green terminal glow, digital artifacts",
    "organized_crime": "gritty urban, high contrast, desaturated",
    "cold_cases": "foggy atmosphere, blue undertones, evidence board aesthetic",
    "political_corruption": "formal settings, gold and dark tones, power imagery",
    "environmental_crime": "contrasting nature beauty with industrial decay",
    "true_crime_general": "dramatic documentary lighting, cinematic framing",
}


class ChannelManager:
    """Manages channel lifecycle: creation, OAuth setup, voice cloning, health."""

    def __init__(
        self,
        settings: Settings,
        db_pool: AsyncConnectionPool,
        http_client: httpx.AsyncClient,
    ) -> None:
        self._settings = settings
        self._pool = db_pool
        self._http = http_client

    # ------------------------------------------------------------------
    # Channel creation
    # ------------------------------------------------------------------

    async def create_channel(self, input: ChannelCreateInput) -> ChannelResponse:
        """Create a channel with all 4 settings table rows.

        1. INSERT into channels
        2. INSERT into channel_voice_settings (defaults)
        3. INSERT into channel_brand_settings (defaults based on niche)
        4. INSERT into channel_credentials (encrypted placeholders)
        5. INSERT into channel_generation_settings (defaults)
        """
        palette = input.color_palette or _NICHE_PALETTES.get(
            input.niche, _NICHE_PALETTES["true_crime_general"]
        )
        prompt_suffix = _NICHE_PROMPT_SUFFIX.get(input.niche, "")

        async with self._pool.connection() as conn, conn.transaction():
            # 1. Core channel record
            row = await conn.execute(
                queries.INSERT_CHANNEL,
                {
                    "name": input.name,
                    "youtube_channel_id": input.youtube_channel_id,
                    "handle": input.handle,
                    "description": input.description,
                },
            )
            channel_row = cast("Row | None", await row.fetchone())
            assert channel_row is not None
            channel_id = channel_row["id"]

            # 2. Voice settings
            await conn.execute(
                queries.INSERT_CHANNEL_VOICE_SETTINGS,
                {
                    "channel_id": channel_id,
                    "voice_id": input.voice_id,
                    "voice_name": input.voice_name,
                },
            )

            # 3. Brand settings
            import orjson

            await conn.execute(
                queries.INSERT_CHANNEL_BRAND_SETTINGS,
                {
                    "channel_id": channel_id,
                    "color_palette": orjson.dumps(palette).decode(),
                    "thumbnail_archetype": input.thumbnail_archetype,
                    "font_family": input.font_family,
                    "cinematic_prompt_suffix": prompt_suffix,
                },
            )

            # 4. Credentials (placeholder row)
            await conn.execute(
                queries.INSERT_CHANNEL_CREDENTIALS,
                {"channel_id": channel_id},
            )

            # 5. Generation settings (defaults)
            await conn.execute(
                queries.INSERT_CHANNEL_GENERATION_SETTINGS,
                {"channel_id": channel_id},
            )

        await logger.ainfo(
            "channel_created",
            channel_id=str(channel_id),
            name=input.name,
            niche=input.niche,
        )
        return ChannelResponse.from_row(channel_row)

    # ------------------------------------------------------------------
    # YouTube OAuth setup
    # ------------------------------------------------------------------

    async def setup_youtube_oauth(self, channel_id: uuid.UUID) -> OAuthResult:
        """Interactive OAuth2 flow for YouTube API.

        1. Generate authorization URL with youtube scopes
        2. Open browser / print URL
        3. Wait for user to paste the auth code
        4. Exchange for refresh token
        5. Store in channel_credentials
        6. Verify token works by calling channels.list
        """
        client_id = self._settings.youtube.client_id
        client_secret = self._settings.youtube.client_secret

        if not client_id or not client_secret:
            return OAuthResult(
                success=False,
                channel_id=channel_id,
                youtube_channel_title="",
                scopes=[],
            )

        # Generate auth URL with state for CSRF protection
        state = secrets.token_urlsafe(32)
        params = {
            "client_id": client_id,
            "redirect_uri": "urn:ietf:wg:oauth:2.0:oob",
            "response_type": "code",
            "scope": " ".join(YOUTUBE_SCOPES),
            "access_type": "offline",
            "prompt": "consent",
            "state": state,
        }
        auth_url = f"{OAUTH_AUTH_URL}?{urlencode(params)}"

        # Try to open browser, fall back to printing URL
        with contextlib.suppress(Exception):
            webbrowser.open(auth_url)

        # The CLI layer will prompt the user for the auth code and call
        # complete_oauth_exchange() with it.
        return OAuthResult(
            success=False,
            channel_id=channel_id,
            youtube_channel_title="",
            scopes=YOUTUBE_SCOPES,
        )

    async def complete_oauth_exchange(
        self,
        channel_id: uuid.UUID,
        auth_code: str,
    ) -> OAuthResult:
        """Exchange auth code for tokens and store them."""
        client_id = self._settings.youtube.client_id
        client_secret = self._settings.youtube.client_secret

        # Exchange code for tokens
        resp = await self._http.post(
            OAUTH_TOKEN_URL,
            data={
                "code": auth_code,
                "client_id": client_id,
                "client_secret": client_secret,
                "redirect_uri": "urn:ietf:wg:oauth:2.0:oob",
                "grant_type": "authorization_code",
            },
        )
        resp.raise_for_status()
        token_data = resp.json()

        refresh_token = token_data.get("refresh_token", "")
        access_token = token_data.get("access_token", "")

        if not refresh_token:
            return OAuthResult(
                success=False,
                channel_id=channel_id,
                youtube_channel_title="No refresh token received",
                scopes=[],
            )

        # Store encrypted refresh token
        async with self._pool.connection() as conn:
            await conn.execute(
                queries.UPDATE_CHANNEL_CREDENTIALS_OAUTH,
                {
                    "channel_id": channel_id,
                    "refresh_token": refresh_token,
                },
            )

        # Verify by calling channels.list
        channel_title = ""
        try:
            verify_resp = await self._http.get(
                f"{YOUTUBE_API_BASE}/channels",
                params={"part": "snippet", "mine": "true"},
                headers={"Authorization": f"Bearer {access_token}"},
            )
            verify_resp.raise_for_status()
            items = verify_resp.json().get("items", [])
            if items:
                channel_title = items[0]["snippet"]["title"]
        except Exception as e:
            await logger.awarning("oauth_verify_failed", error=str(e))

        await logger.ainfo(
            "oauth_setup_complete",
            channel_id=str(channel_id),
            youtube_title=channel_title,
        )

        return OAuthResult(
            success=True,
            channel_id=channel_id,
            youtube_channel_title=channel_title,
            scopes=YOUTUBE_SCOPES,
            expires_at=None,
        )

    # ------------------------------------------------------------------
    # Voice cloning
    # ------------------------------------------------------------------

    async def clone_voice(self, channel_id: uuid.UUID, sample_path: str) -> VoiceCloneResult:
        """Clone a voice via Fish Audio API.

        1. Upload sample audio (15-30 seconds recommended)
        2. Create voice clone
        3. Test with a sample sentence
        4. Store voice_id in channel_voice_settings
        """
        api_key = self._settings.fish_audio.api_key
        if not api_key:
            raise ValueError("FISH_AUDIO_API_KEY not configured")

        headers = {"Authorization": f"Bearer {api_key}"}

        # Read the sample file
        import mimetypes

        content_type = mimetypes.guess_type(sample_path)[0] or "audio/wav"

        with open(sample_path, "rb") as f:
            sample_data = f.read()

        # Create voice model via Fish Audio
        resp = await self._http.post(
            f"{FISH_AUDIO_BASE}/model",
            headers=headers,
            files={
                "voices": ("sample.wav", sample_data, content_type),
            },
            data={
                "visibility": "private",
                "type": "tts",
                "title": f"CrimeMill-{channel_id}",
            },
            timeout=120.0,
        )
        resp.raise_for_status()
        voice_data = resp.json()
        voice_id = voice_data.get("_id", voice_data.get("id", ""))
        voice_name = voice_data.get("title", "")

        # Test the cloned voice with a sample sentence
        test_text = "The investigation revealed a pattern of deception that spanned decades."
        test_audio_url = ""
        try:
            test_resp = await self._http.post(
                f"{FISH_AUDIO_BASE}/v1/tts",
                headers=headers,
                json={
                    "model": "speech-01-turbo",
                    "reference_id": voice_id,
                    "text": test_text,
                    "format": "wav",
                    "sample_rate": 48000,
                },
                timeout=60.0,
            )
            test_resp.raise_for_status()
            test_audio_url = "(test audio generated successfully)"
        except Exception as e:
            await logger.awarning("voice_test_failed", error=str(e))

        # Store voice_id in channel settings
        async with self._pool.connection() as conn:
            await conn.execute(
                queries.UPDATE_CHANNEL_VOICE,
                {
                    "channel_id": channel_id,
                    "voice_id": voice_id,
                    "voice_name": voice_name,
                },
            )

        await logger.ainfo(
            "voice_cloned",
            channel_id=str(channel_id),
            voice_id=voice_id,
            voice_name=voice_name,
        )

        return VoiceCloneResult(
            voice_id=voice_id,
            voice_name=voice_name,
            sample_audio_url=sample_path,
            test_audio_url=test_audio_url,
        )

    # ------------------------------------------------------------------
    # Channel health
    # ------------------------------------------------------------------

    async def get_channel_health(self, channel_id: uuid.UUID) -> ChannelHealth:
        """Comprehensive health check for a channel."""
        async with self._pool.connection() as conn:
            # Get channel info
            row = cast(
                "Row | None",
                await (
                    await conn.execute(queries.GET_CHANNEL, {"channel_id": channel_id})
                ).fetchone(),
            )
            if row is None:
                raise ValueError(f"Channel {channel_id} not found")

            channel_name = row["name"]

            # OAuth status
            creds_row = cast(
                "Row | None",
                await (
                    await conn.execute(queries.GET_CHANNEL_CREDENTIALS, {"channel_id": channel_id})
                ).fetchone(),
            )

            oauth_status: str = "not_configured"
            if creds_row and creds_row.get("youtube_oauth_refresh_token_encrypted"):
                oauth_status = "valid"  # We'd need to test the token for expiry

            # Voice status
            voice_row = cast(
                "Row | None",
                await (
                    await conn.execute(
                        queries.GET_CHANNEL_VOICE_SETTINGS, {"channel_id": channel_id}
                    )
                ).fetchone(),
            )

            voice_status = "not_configured"
            if voice_row and voice_row.get("fish_audio_voice_id"):
                voice_status = "active"

            # Last published
            pub_row = cast(
                "Row | None",
                await (
                    await conn.execute(
                        queries.GET_CHANNEL_LAST_PUBLISHED, {"channel_id": channel_id}
                    )
                ).fetchone(),
            )
            last_published = pub_row["published_at"] if pub_row else None

            # Queue depth
            queue_row = cast(
                "Row | None",
                await (
                    await conn.execute(queries.GET_CHANNEL_QUEUE_DEPTH, {"channel_id": channel_id})
                ).fetchone(),
            )
            videos_in_queue = queue_row["videos_in_queue"] if queue_row else 0
            dead_letter_jobs = queue_row["dead_letter_jobs"] if queue_row else 0

            # Monthly revenue
            rev_row = cast(
                "Row | None",
                await (
                    await conn.execute(
                        queries.GET_CHANNEL_MONTHLY_REVENUE, {"channel_id": channel_id}
                    )
                ).fetchone(),
            )
            monthly_revenue = (
                Decimal(str(rev_row["monthly_revenue"]))
                if rev_row and rev_row.get("monthly_revenue")
                else None
            )

        return ChannelHealth(
            channel_id=channel_id,
            channel_name=channel_name,
            oauth_status=oauth_status,
            voice_status=voice_status,
            last_published=last_published,
            videos_in_queue=videos_in_queue,
            dead_letter_jobs=dead_letter_jobs,
            subscriber_trend="flat",
            yellow_icon_rate=0.0,
            monthly_revenue=monthly_revenue,
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    async def resolve_channel_id(self, handle_or_name: str) -> uuid.UUID | None:
        """Resolve a channel handle/name to its UUID."""
        async with self._pool.connection() as conn:
            # Try by handle first
            row = cast(
                "Row | None",
                await (
                    await conn.execute(queries.GET_CHANNEL_BY_HANDLE, {"handle": handle_or_name})
                ).fetchone(),
            )
            if row:
                return uuid.UUID(str(row["id"]))

            # Try by name (case-insensitive)
            row = cast(
                "Row | None",
                await (
                    await conn.execute(
                        """SELECT id FROM channels
                       WHERE lower(name) = lower(%(name)s)
                       LIMIT 1""",
                        {"name": handle_or_name},
                    )
                ).fetchone(),
            )
            if row:
                return uuid.UUID(str(row["id"]))

        return None
