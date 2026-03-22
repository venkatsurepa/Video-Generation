"""Podcast distribution service — Buzzsprout API integration.

Extracts audio from published YouTube videos, normalizes to podcast standards
(-16 LUFS, MP3 128 kbps mono), generates episode metadata, and publishes
via the Buzzsprout REST API.  Optionally prepends an intro and appends an
outro bumper before upload.
"""

from __future__ import annotations

import asyncio
import os
import tempfile
from datetime import UTC
from decimal import Decimal
from typing import TYPE_CHECKING, Any

import structlog

from src.models.podcast import (
    BuzzsproutEpisode,
    EpisodeMetadata,
    PodcastEpisodeResult,
    PodcastStats,
)
from src.utils.retry import async_retry

if TYPE_CHECKING:
    import uuid

    import httpx

    from src.config import Settings

logger = structlog.get_logger()

# ---------------------------------------------------------------------------
# Buzzsprout API
# ---------------------------------------------------------------------------

BUZZSPROUT_API_BASE: str = "https://www.buzzsprout.com/api"

# Podcast audio target profile (EBU R128 compliant for podcasting)
PODCAST_TARGET_LUFS: float = -16.0
PODCAST_BITRATE: str = "128k"
PODCAST_SAMPLE_RATE: int = 44100
PODCAST_CHANNELS: int = 1  # mono

# Buzzsprout upload limit
MAX_UPLOAD_SIZE_MB: int = 250


class PodcastPublishError(Exception):
    """Raised when podcast publishing fails unrecoverably."""


class PodcastPublisher:
    """Publishes podcast episodes to Buzzsprout from finished video audio."""

    def __init__(self, settings: Settings, http_client: httpx.AsyncClient) -> None:
        self._settings = settings
        self._http = http_client
        self._podcast_id = settings.buzzsprout.podcast_id
        self._api_token = settings.buzzsprout.api_key

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def publish_episode(
        self,
        video_id: uuid.UUID,
        audio_storage_path: str,
        title: str,
        description: str,
        tags: list[str],
        episode_number: int,
        youtube_video_id: str | None = None,
        season_number: int | None = None,
        intro_path: str | None = None,
        outro_path: str | None = None,
    ) -> PodcastEpisodeResult:
        """Full podcast publishing pipeline.

        1. Download audio from R2 to temp directory
        2. Optionally prepend intro / append outro
        3. Normalize to podcast standards (-16 LUFS, MP3 128k mono)
        4. Generate episode metadata
        5. Upload to Buzzsprout
        6. Return result with episode ID and cost info
        """
        await logger.ainfo(
            "podcast_publish_start",
            video_id=str(video_id),
            episode_number=episode_number,
        )

        with tempfile.TemporaryDirectory(prefix="crimemill_podcast_") as tmp_dir:
            # Step 1: Download source audio from R2
            source_audio = os.path.join(tmp_dir, "source_audio.wav")
            await self._download_audio(audio_storage_path, source_audio)

            # Step 2: Prepend intro / append outro if provided
            assembled_audio = source_audio
            if intro_path or outro_path:
                assembled_audio = os.path.join(tmp_dir, "assembled.wav")
                await self._concat_bumpers(
                    source_audio, assembled_audio, intro_path, outro_path, tmp_dir
                )

            # Step 3: Normalize to podcast profile
            podcast_mp3 = os.path.join(tmp_dir, "episode.mp3")
            await self._normalize_for_podcast(assembled_audio, podcast_mp3)

            # Step 4: Validate file size
            file_size = os.path.getsize(podcast_mp3)
            if file_size > MAX_UPLOAD_SIZE_MB * 1024 * 1024:
                raise PodcastPublishError(
                    f"Podcast file too large: {file_size / 1024 / 1024:.1f}MB "
                    f"(max {MAX_UPLOAD_SIZE_MB}MB)"
                )

            # Step 5: Get duration
            duration = await self._get_duration(podcast_mp3)

            # Step 6: Build metadata
            youtube_url = (
                f"https://www.youtube.com/watch?v={youtube_video_id}" if youtube_video_id else ""
            )
            metadata = self._build_metadata(
                title=title,
                description=description,
                tags=tags,
                episode_number=episode_number,
                season_number=season_number,
                custom_url=youtube_url,
            )

            # Step 7: Upload to Buzzsprout
            episode = await self._upload_to_buzzsprout(podcast_mp3, metadata)

            # Step 8: Upload normalized audio to R2 for archival
            podcast_r2_key = f"podcasts/{video_id}/episode_{episode_number}.mp3"
            await self._upload_to_r2(podcast_mp3, podcast_r2_key)

            await logger.ainfo(
                "podcast_publish_complete",
                video_id=str(video_id),
                buzzsprout_id=episode.id,
                duration_seconds=duration,
                file_size_bytes=file_size,
            )

            return PodcastEpisodeResult(
                video_id=video_id,
                buzzsprout_episode_id=episode.id,
                audio_file_path=podcast_r2_key,
                duration_seconds=duration,
                file_size_bytes=file_size,
                rss_feed_url=f"https://feeds.buzzsprout.com/{self._podcast_id}.rss",
                cost_usd=Decimal("0.00"),  # Buzzsprout is flat-rate, no per-episode cost
            )

    async def get_episode_stats(self, episode_id: int) -> PodcastStats:
        """Fetch download stats for a single episode from Buzzsprout."""
        url = f"{BUZZSPROUT_API_BASE}/{self._podcast_id}/episodes/{episode_id}/stats.json"
        resp = await self._http.get(url, headers=self._auth_headers())
        resp.raise_for_status()
        data: dict[str, Any] = resp.json()

        total_downloads = sum(day.get("total_downloads", 0) for day in data.get("days", []))
        recent_downloads = sum(day.get("total_downloads", 0) for day in data.get("days", [])[-30:])

        return PodcastStats(
            episode_id=episode_id,
            total_downloads=total_downloads,
            downloads_30_day=recent_downloads,
        )

    async def get_all_episodes(self) -> list[BuzzsproutEpisode]:
        """List all episodes from Buzzsprout."""
        url = f"{BUZZSPROUT_API_BASE}/{self._podcast_id}/episodes.json"
        resp = await self._http.get(url, headers=self._auth_headers())
        resp.raise_for_status()
        return [BuzzsproutEpisode.model_validate(ep) for ep in resp.json()]

    # ------------------------------------------------------------------
    # Buzzsprout API
    # ------------------------------------------------------------------

    @async_retry(max_attempts=3, base_delay=2.0)
    async def _upload_to_buzzsprout(
        self,
        audio_path: str,
        metadata: EpisodeMetadata,
    ) -> BuzzsproutEpisode:
        """Upload an episode to Buzzsprout via multipart POST."""
        url = f"{BUZZSPROUT_API_BASE}/{self._podcast_id}/episodes.json"

        file_size = os.path.getsize(audio_path)
        await logger.ainfo(
            "buzzsprout_upload_start",
            file_size_mb=round(file_size / 1024 / 1024, 2),
        )

        data: dict[str, Any] = {
            "title": metadata.title,
            "description": metadata.description,
            "summary": metadata.summary,
            "tags": ",".join(metadata.tags),
            "episode_number": str(metadata.episode_number),
            "explicit": str(metadata.explicit).lower(),
            "private": "false",
            "custom_url": metadata.custom_url,
        }
        if metadata.season_number is not None:
            data["season_number"] = str(metadata.season_number)

        with open(audio_path, "rb") as f:
            files = {"audio_file": ("episode.mp3", f, "audio/mpeg")}
            resp = await self._http.post(
                url,
                headers=self._auth_headers(),
                data=data,
                files=files,
                timeout=300.0,
            )

        resp.raise_for_status()
        result = resp.json()

        await logger.ainfo("buzzsprout_upload_complete", episode_id=result.get("id"))
        return BuzzsproutEpisode.model_validate(result)

    # ------------------------------------------------------------------
    # Audio normalization (FFmpeg)
    # ------------------------------------------------------------------

    async def _normalize_for_podcast(self, input_path: str, output_path: str) -> None:
        """Two-pass EBU R128 loudness normalization to podcast standards.

        Pass 1: Measure integrated loudness, LRA, true peak.
        Pass 2: Apply correction to hit -16 LUFS, -1.5 dBTP, mono, 128k MP3.
        """
        await logger.ainfo("podcast_normalize_start")

        # Pass 1: Measure loudness
        measure_cmd = [
            "ffmpeg",
            "-hide_banner",
            "-i",
            input_path,
            "-af",
            f"loudnorm=I={PODCAST_TARGET_LUFS}:TP=-1.5:LRA=11:print_format=json",
            "-f",
            "null",
            "-",
        ]
        proc = await asyncio.create_subprocess_exec(
            *measure_cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr_bytes = await proc.communicate()
        if proc.returncode != 0:
            raise PodcastPublishError(
                f"FFmpeg loudness measurement failed: {stderr_bytes.decode()[:500]}"
            )

        # Parse loudnorm JSON from stderr
        stderr_text = stderr_bytes.decode()
        loudnorm_stats = self._parse_loudnorm_json(stderr_text)

        # Pass 2: Apply normalization and encode
        normalize_filter = (
            f"loudnorm=I={PODCAST_TARGET_LUFS}:TP=-1.5:LRA=11"
            f":measured_I={loudnorm_stats['input_i']}"
            f":measured_TP={loudnorm_stats['input_tp']}"
            f":measured_LRA={loudnorm_stats['input_lra']}"
            f":measured_thresh={loudnorm_stats['input_thresh']}"
            f":offset={loudnorm_stats['target_offset']}"
            ":linear=true"
        )

        encode_cmd = [
            "ffmpeg",
            "-hide_banner",
            "-y",
            "-i",
            input_path,
            "-af",
            normalize_filter,
            "-ac",
            str(PODCAST_CHANNELS),
            "-ar",
            str(PODCAST_SAMPLE_RATE),
            "-codec:a",
            "libmp3lame",
            "-b:a",
            PODCAST_BITRATE,
            "-id3v2_version",
            "3",
            output_path,
        ]
        proc = await asyncio.create_subprocess_exec(
            *encode_cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr_bytes = await proc.communicate()
        if proc.returncode != 0:
            raise PodcastPublishError(f"FFmpeg encode failed: {stderr_bytes.decode()[:500]}")

        await logger.ainfo(
            "podcast_normalize_complete",
            output_path=output_path,
            file_size_mb=round(os.path.getsize(output_path) / 1024 / 1024, 2),
        )

    @staticmethod
    def _parse_loudnorm_json(stderr: str) -> dict[str, str]:
        """Extract the loudnorm JSON block from FFmpeg stderr."""
        import json

        # loudnorm prints a JSON blob in stderr; find the last { ... } block
        brace_depth = 0
        json_start = -1
        json_end = -1
        for i in range(len(stderr) - 1, -1, -1):
            if stderr[i] == "}":
                if brace_depth == 0:
                    json_end = i + 1
                brace_depth += 1
            elif stderr[i] == "{":
                brace_depth -= 1
                if brace_depth == 0:
                    json_start = i
                    break

        if json_start == -1:
            raise PodcastPublishError("Could not parse loudnorm stats from FFmpeg output")

        stats: dict[str, str] = json.loads(stderr[json_start:json_end])
        return stats

    # ------------------------------------------------------------------
    # Audio concatenation (intro/outro bumpers)
    # ------------------------------------------------------------------

    async def _concat_bumpers(
        self,
        main_audio: str,
        output_path: str,
        intro_path: str | None,
        outro_path: str | None,
        tmp_dir: str,
    ) -> None:
        """Concatenate intro + main + outro using FFmpeg concat demuxer."""
        concat_list = os.path.join(tmp_dir, "concat.txt")
        parts: list[str] = []
        if intro_path:
            parts.append(intro_path)
        parts.append(main_audio)
        if outro_path:
            parts.append(outro_path)

        with open(concat_list, "w") as f:
            for part in parts:
                safe_path = part.replace("'", "'\\''")
                f.write(f"file '{safe_path}'\n")

        cmd = [
            "ffmpeg",
            "-hide_banner",
            "-y",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            concat_list,
            "-c",
            "copy",
            output_path,
        ]
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr_bytes = await proc.communicate()
        if proc.returncode != 0:
            raise PodcastPublishError(f"FFmpeg concat failed: {stderr_bytes.decode()[:500]}")

    # ------------------------------------------------------------------
    # Duration probe
    # ------------------------------------------------------------------

    async def _get_duration(self, audio_path: str) -> float:
        """Get audio duration in seconds via ffprobe."""
        cmd = [
            "ffprobe",
            "-v",
            "quiet",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            audio_path,
        ]
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout_bytes, _ = await proc.communicate()
        try:
            return float(stdout_bytes.decode().strip())
        except ValueError:
            return 0.0

    # ------------------------------------------------------------------
    # Storage helpers
    # ------------------------------------------------------------------

    async def _download_audio(self, storage_path: str, destination: str) -> None:
        """Download audio from R2 to a local path."""
        from src.utils.storage import R2Client

        r2 = R2Client(
            account_id=self._settings.storage.account_id,
            access_key_id=self._settings.storage.access_key_id,
            secret_access_key=self._settings.storage.secret_access_key,
        )
        await asyncio.to_thread(
            r2.download_file,
            self._settings.storage.bucket_name,
            storage_path,
            destination,
        )

    async def _upload_to_r2(self, local_path: str, r2_key: str) -> None:
        """Upload the normalized podcast MP3 to R2 for archival."""
        from src.utils.storage import R2Client

        r2 = R2Client(
            account_id=self._settings.storage.account_id,
            access_key_id=self._settings.storage.access_key_id,
            secret_access_key=self._settings.storage.secret_access_key,
        )
        await asyncio.to_thread(
            r2.upload_file,
            self._settings.storage.bucket_name,
            r2_key,
            local_path,
            "audio/mpeg",
        )

    # ------------------------------------------------------------------
    # Metadata generation
    # ------------------------------------------------------------------

    @staticmethod
    def _build_metadata(
        title: str,
        description: str,
        tags: list[str],
        episode_number: int,
        season_number: int | None = None,
        custom_url: str = "",
    ) -> EpisodeMetadata:
        """Build Buzzsprout episode metadata from video data."""
        from datetime import datetime

        # Podcast title: prefix with episode number for feed ordering
        podcast_title = f"Ep. {episode_number}: {title}"

        # HTML description with YouTube cross-link and AI disclosure
        html_desc_parts = [f"<p>{description}</p>"]
        if custom_url:
            html_desc_parts.append(
                f"<p><strong>Watch the full video:</strong> "
                f'<a href="{custom_url}">{custom_url}</a></p>'
            )
        html_desc_parts.append(
            "<p><em>This podcast uses AI-assisted production tools "
            "for narration and research.</em></p>"
        )
        html_description = "\n".join(html_desc_parts)

        # Plain text summary (max 255 chars for Buzzsprout)
        summary = description[:252] + "..." if len(description) > 255 else description

        return EpisodeMetadata(
            title=podcast_title,
            description=html_description,
            summary=summary,
            tags=tags[:10],  # Buzzsprout limits tags
            episode_number=episode_number,
            season_number=season_number,
            custom_url=custom_url,
            published_at=datetime.now(UTC),
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _auth_headers(self) -> dict[str, str]:
        """Build Buzzsprout API auth headers."""
        return {
            "Authorization": f"Token token={self._api_token}",
            "Content-Type": "application/json",
        }
