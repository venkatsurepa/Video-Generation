"""YouTube upload service — 5-step safety upload flow.

Implements the complete upload lifecycle:
  1. Upload video as PRIVATE via resumable upload protocol
  2. Poll for processing completion and ad-suitability check
  3. Check for Content ID claims
  4. Evaluate results (green/yellow → publish, red/claims → unlisted)
  5. Publish, set thumbnail, add to playlist

All HTTP calls go through ``httpx`` — no google-api-python-client dependency.
OAuth2 refresh tokens are stored per-channel in ``channel_credentials`` and
exchanged for short-lived access tokens cached in memory.
"""

from __future__ import annotations

import asyncio
import mimetypes
import random
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any

import httpx
import structlog

from src.models.youtube import (
    VideoStats,
    VideoUploadInput,
    YouTubeUploadResult,
    YouTubeVideoStatus,
)

if TYPE_CHECKING:
    import uuid

    from src.config import Settings

logger = structlog.get_logger()


# ---------------------------------------------------------------------------
# YouTube API endpoints
# ---------------------------------------------------------------------------

YOUTUBE_API_BASE: str = "https://www.googleapis.com/youtube/v3"
YOUTUBE_UPLOAD_BASE: str = "https://www.googleapis.com/upload/youtube/v3"
OAUTH_TOKEN_URL: str = "https://oauth2.googleapis.com/token"


# ---------------------------------------------------------------------------
# Upload tuning
# ---------------------------------------------------------------------------

CHUNK_SIZE: int = 10 * 1024 * 1024  # 10 MB per chunk
MIN_CHUNK_SIZE: int = 256 * 1024  # 256 KB minimum (except final)
MAX_UPLOAD_RETRIES: int = 10  # per the bible
MAX_API_RETRIES: int = 3
RETRY_CAP_SECONDS: float = 64.0  # 2^n × random(), capped here
UPLOAD_TIMEOUT: float = 300.0  # 5 min per chunk PUT
API_TIMEOUT: float = 30.0

# Processing poll
POLL_INTERVAL_SECONDS: int = 60
POLL_TIMEOUT_SECONDS: int = 3_600  # 60 minutes

# OAuth token caching — refresh 5 min before real expiry
TOKEN_REFRESH_BUFFER_SECONDS: int = 300

# Description byte limit enforced by YouTube
MAX_DESCRIPTION_BYTES: int = 5_000
MAX_TAGS_CHARS: int = 500
MAX_THUMBNAIL_BYTES: int = 2 * 1024 * 1024  # 2 MB


# ---------------------------------------------------------------------------
# Quota costs (from the project bible Section 2.3)
# ---------------------------------------------------------------------------

QUOTA_VIDEO_INSERT: int = 100
QUOTA_VIDEO_UPDATE: int = 50
QUOTA_VIDEO_LIST: int = 1
QUOTA_THUMBNAIL_SET: int = 50
QUOTA_PLAYLIST_INSERT: int = 50
QUOTA_CAPTION_INSERT: int = 400


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class YouTubeUploadError(Exception):
    """Base error for YouTube upload failures."""


class UploadSessionExpiredError(YouTubeUploadError):
    """404 on the resumable upload URI — session expired, must restart."""


class QuotaExceededError(YouTubeUploadError):
    """YouTube Data API daily quota exhausted."""


class ContentFilteredError(YouTubeUploadError):
    """Video rejected by YouTube's content policies."""


# ---------------------------------------------------------------------------
# YouTubeUploader
# ---------------------------------------------------------------------------


class YouTubeUploader:
    """Uploads finished videos to YouTube via the Data API v3.

    Implements the 5-step safety upload flow:

    1. Upload as **private** via resumable upload.
    2. Poll until YouTube finishes processing; read ad-suitability signal.
    3. Check for Content ID claims via ``contentDetails.contentRating``.
    4. Evaluate: green/yellow → publish; red or claims → set unlisted for
       human review.
    5. Publish (or schedule), set thumbnail, add to playlist.

    Parameters
    ----------
    settings:
        Application settings — must contain ``youtube.client_id``,
        ``youtube.client_secret``, and ``database`` settings for credential
        retrieval via the Supabase REST API.
    http_client:
        Shared ``httpx.AsyncClient`` used for all HTTP calls.
    """

    def __init__(self, settings: Settings, http_client: httpx.AsyncClient) -> None:
        self._settings = settings
        self._http = http_client
        # In-memory OAuth cache: channel_id → (access_token, expires_at_monotonic)
        self._token_cache: dict[uuid.UUID, tuple[str, float]] = {}

    # ==================================================================
    # Public API
    # ==================================================================

    async def upload_video(
        self,
        video: VideoUploadInput,
    ) -> YouTubeUploadResult:
        """Execute the complete 5-step safety upload flow.

        Parameters
        ----------
        video:
            All metadata and file paths needed for the upload.

        Returns
        -------
        YouTubeUploadResult
            Upload outcome including YouTube video ID, suitability verdict,
            claim info, and quota usage.

        Raises
        ------
        YouTubeUploadError
            On any unrecoverable failure (session expired twice, processing
            rejected, quota exceeded, etc.).
        """
        t0 = time.monotonic()
        quota_used = 0

        await logger.ainfo(
            "upload_started",
            video_id=str(video.video_id),
            channel_id=str(video.channel_id),
            file_path=video.file_path,
        )

        # ----------------------------------------------------------
        # Step 1 — Upload as PRIVATE via resumable upload
        # ----------------------------------------------------------
        access_token = await self._get_access_token(video.channel_id)
        metadata = _build_upload_metadata(video)

        # Allow one restart if the session expires mid-upload
        youtube_video_id: str | None = None
        for upload_attempt in range(2):
            try:
                upload_uri = await self._initiate_resumable_upload(
                    access_token,
                    metadata,
                    video.file_path,
                )
                youtube_video_id = await self._upload_file_resumable(
                    upload_uri,
                    video.file_path,
                )
                break
            except UploadSessionExpiredError:
                if upload_attempt == 0:
                    await logger.awarning(
                        "upload_session_expired_restarting",
                        video_id=str(video.video_id),
                    )
                    # Refresh token in case it also expired
                    access_token = await self._get_access_token(video.channel_id)
                    continue
                raise YouTubeUploadError("Upload session expired twice — aborting") from None

        if youtube_video_id is None:
            raise YouTubeUploadError("Upload loop exited without a video ID")

        quota_used += QUOTA_VIDEO_INSERT

        await logger.ainfo(
            "upload_step1_complete",
            video_id=str(video.video_id),
            youtube_video_id=youtube_video_id,
        )

        # ----------------------------------------------------------
        # Step 2 — Poll for processing & ad suitability
        # ----------------------------------------------------------
        ad_suitability, poll_quota = await self._poll_processing(
            youtube_video_id,
            video.channel_id,
        )
        quota_used += poll_quota

        await logger.ainfo(
            "upload_step2_complete",
            youtube_video_id=youtube_video_id,
            ad_suitability=ad_suitability,
        )

        # ----------------------------------------------------------
        # Step 3 — Check Content ID claims
        # ----------------------------------------------------------
        claims = await self._check_content_id_claims(
            youtube_video_id,
            video.channel_id,
        )
        quota_used += QUOTA_VIDEO_LIST

        await logger.ainfo(
            "upload_step3_complete",
            youtube_video_id=youtube_video_id,
            claims_count=len(claims),
        )

        # ----------------------------------------------------------
        # Step 4 — Evaluate
        # ----------------------------------------------------------
        should_publish = ad_suitability in ("green", "yellow") and not claims

        if ad_suitability == "yellow":
            await logger.awarning(
                "limited_ad_suitability",
                youtube_video_id=youtube_video_id,
                message="Yellow icon — limited ads.  Proceeding with publish.",
            )

        if claims:
            await logger.awarning(
                "content_id_claims_found",
                youtube_video_id=youtube_video_id,
                claims=claims,
            )

        # ----------------------------------------------------------
        # Step 5 — Publish (or set unlisted for human review)
        # ----------------------------------------------------------
        if should_publish:
            if video.scheduled_publish_at:
                privacy_status = "private"
                await self._update_video_status(
                    youtube_video_id,
                    video.channel_id,
                    privacy_status="private",
                    publish_at=video.scheduled_publish_at.isoformat(),
                )
            else:
                privacy_status = "public"
                await self._update_video_status(
                    youtube_video_id,
                    video.channel_id,
                    privacy_status="public",
                )
        else:
            privacy_status = "unlisted"
            await self._update_video_status(
                youtube_video_id,
                video.channel_id,
                privacy_status="unlisted",
            )
            await logger.awarning(
                "video_set_unlisted",
                youtube_video_id=youtube_video_id,
                ad_suitability=ad_suitability,
                claims_count=len(claims),
                message="Red icon or claims detected — set unlisted for human review.",
            )

        quota_used += QUOTA_VIDEO_UPDATE

        # Thumbnail
        thumbnail_set = False
        if video.thumbnail_path:
            thumbnail_set = await self.set_thumbnail(
                youtube_video_id,
                video.thumbnail_path,
                video.channel_id,
            )
            quota_used += QUOTA_THUMBNAIL_SET

        # Playlist
        playlist_added = False
        if video.playlist_id:
            playlist_added = await self.add_to_playlist(
                youtube_video_id,
                video.playlist_id,
                video.channel_id,
            )
            quota_used += QUOTA_PLAYLIST_INSERT

        # Captions
        captions_uploaded = False
        if video.srt_path:
            captions_uploaded = await self.upload_captions(
                youtube_video_id,
                video.srt_path,
                video.channel_id,
            )
            quota_used += QUOTA_CAPTION_INSERT

        elapsed = round(time.monotonic() - t0, 2)

        await logger.ainfo(
            "upload_complete",
            video_id=str(video.video_id),
            youtube_video_id=youtube_video_id,
            privacy_status=privacy_status,
            ad_suitability=ad_suitability,
            quota_used=quota_used,
            duration_seconds=elapsed,
        )

        return YouTubeUploadResult(
            youtube_video_id=youtube_video_id,
            youtube_url=f"https://youtu.be/{youtube_video_id}",
            privacy_status=privacy_status,
            ad_suitability=ad_suitability,
            content_id_claims=claims,
            thumbnail_set=thumbnail_set,
            playlist_added=playlist_added,
            captions_uploaded=captions_uploaded,
            quota_units_used=quota_used,
            upload_duration_seconds=elapsed,
        )

    # ------------------------------------------------------------------

    async def set_thumbnail(
        self,
        video_id: str,
        thumbnail_path: str,
        channel_id: uuid.UUID,
    ) -> bool:
        """Upload a custom thumbnail image.  Max 2 MB.  Cost: 50 quota units.

        Returns ``True`` on success, ``False`` on failure (logged, not raised).
        """
        path = Path(thumbnail_path)
        if not path.exists():
            await logger.aerror("thumbnail_file_missing", path=thumbnail_path)
            return False

        file_size = path.stat().st_size
        if file_size > MAX_THUMBNAIL_BYTES:
            await logger.aerror(
                "thumbnail_too_large",
                path=thumbnail_path,
                size=file_size,
                max_size=MAX_THUMBNAIL_BYTES,
            )
            return False

        content_type = mimetypes.guess_type(thumbnail_path)[0] or "image/jpeg"

        try:
            resp = await self._api_request(
                "POST",
                f"{YOUTUBE_UPLOAD_BASE}/thumbnails/set",
                channel_id=channel_id,
                params={"videoId": video_id},
                content=path.read_bytes(),
                headers={"Content-Type": content_type},
                timeout=60.0,
            )
            resp.raise_for_status()
            await logger.ainfo("thumbnail_set", youtube_video_id=video_id)
            return True
        except Exception:
            await logger.aexception("thumbnail_set_failed", youtube_video_id=video_id)
            return False

    # ------------------------------------------------------------------

    async def add_to_playlist(
        self,
        video_id: str,
        playlist_id: str,
        channel_id: uuid.UUID,
    ) -> bool:
        """Add video to a playlist.  Cost: 50 quota units.

        Returns ``True`` on success, ``False`` on failure (logged, not raised).
        """
        body = {
            "snippet": {
                "playlistId": playlist_id,
                "resourceId": {
                    "kind": "youtube#video",
                    "videoId": video_id,
                },
            },
        }

        try:
            resp = await self._api_request(
                "POST",
                f"{YOUTUBE_API_BASE}/playlistItems",
                channel_id=channel_id,
                params={"part": "snippet"},
                json=body,
            )
            resp.raise_for_status()
            await logger.ainfo(
                "playlist_added",
                youtube_video_id=video_id,
                playlist_id=playlist_id,
            )
            return True
        except Exception:
            await logger.aexception(
                "playlist_add_failed",
                youtube_video_id=video_id,
                playlist_id=playlist_id,
            )
            return False

    # ------------------------------------------------------------------

    async def create_playlist(
        self,
        title: str,
        description: str,
        channel_id: uuid.UUID,
        privacy_status: str = "public",
    ) -> str | None:
        """Create a new YouTube playlist.  Cost: 50 quota units.

        Returns the playlist ID on success, ``None`` on failure (logged, not
        raised).
        """
        body = {
            "snippet": {
                "title": title,
                "description": description,
            },
            "status": {
                "privacyStatus": privacy_status,
            },
        }

        try:
            resp = await self._api_request(
                "POST",
                f"{YOUTUBE_API_BASE}/playlists",
                channel_id=channel_id,
                params={"part": "snippet,status"},
                json=body,
            )
            resp.raise_for_status()
            data = resp.json()
            playlist_id: str = data["id"]
            await logger.ainfo(
                "playlist_created",
                playlist_id=playlist_id,
                title=title,
            )
            return playlist_id
        except Exception:
            await logger.aexception(
                "playlist_create_failed",
                title=title,
            )
            return None

    # ------------------------------------------------------------------

    async def upload_captions(
        self,
        video_id: str,
        srt_path: str,
        channel_id: uuid.UUID,
        language: str = "en",
    ) -> bool:
        """Upload an SRT caption file.  Cost: 400 quota units — expensive.

        Consider using YouTube Studio's manual upload for non-automated flows
        to save quota.

        Returns ``True`` on success, ``False`` on failure (logged, not raised).
        """
        path = Path(srt_path)
        if not path.exists():
            await logger.aerror("srt_file_missing", path=srt_path)
            return False

        caption_metadata = {
            "snippet": {
                "videoId": video_id,
                "language": language,
                "name": language,
                "isDraft": False,
            },
        }

        # YouTube captions.insert uses multipart: metadata JSON + file body.
        # With uploadType=multipart the body is a multipart/related message.
        # httpx doesn't natively produce multipart/related, so we build it
        # manually with a boundary.
        import secrets

        boundary = f"crimemill-{secrets.token_hex(8)}"
        srt_bytes = path.read_bytes()

        body_parts = (
            (
                f"--{boundary}\r\n"
                f"Content-Type: application/json; charset=UTF-8\r\n\r\n"
                f"{_json_dumps(caption_metadata)}\r\n"
                f"--{boundary}\r\n"
                f"Content-Type: application/octet-stream\r\n\r\n"
            ).encode()
            + srt_bytes
            + f"\r\n--{boundary}--".encode()
        )

        try:
            resp = await self._api_request(
                "POST",
                f"{YOUTUBE_UPLOAD_BASE}/captions",
                channel_id=channel_id,
                params={"uploadType": "multipart", "part": "snippet"},
                content=body_parts,
                headers={
                    "Content-Type": f"multipart/related; boundary={boundary}",
                },
                timeout=120.0,
            )
            resp.raise_for_status()
            await logger.ainfo(
                "captions_uploaded",
                youtube_video_id=video_id,
                language=language,
            )
            return True
        except Exception:
            await logger.aexception(
                "caption_upload_failed",
                youtube_video_id=video_id,
            )
            return False

    # ------------------------------------------------------------------

    async def get_video_status(
        self,
        video_id: str,
        channel_id: uuid.UUID,
    ) -> YouTubeVideoStatus:
        """Fetch video status and content details.  Cost: 1 quota unit.

        Used for polling suitability during the upload flow and for general
        monitoring.
        """
        resp = await self._api_request(
            "GET",
            f"{YOUTUBE_API_BASE}/videos",
            channel_id=channel_id,
            params={"part": "status,contentDetails", "id": video_id},
        )
        resp.raise_for_status()
        data = resp.json()

        if not data.get("items"):
            raise YouTubeUploadError(f"Video {video_id} not found on YouTube")

        item = data["items"][0]
        status = item["status"]
        content_rating = item.get("contentDetails", {}).get("contentRating", {})

        upload_status: str = status["uploadStatus"]
        rating_flags = list(content_rating.keys())

        # Infer ad suitability from available API signals.
        # The actual green/yellow/red icons are YouTube-Studio-only; we
        # approximate using what the Data API exposes.
        if upload_status != "processed":
            ad_suitability = "pending"
        elif status.get("rejectionReason"):
            ad_suitability = "red"
        elif rating_flags:
            ad_suitability = "yellow"
        else:
            ad_suitability = "green"

        return YouTubeVideoStatus(
            youtube_video_id=video_id,
            upload_status=upload_status,
            privacy_status=status["privacyStatus"],
            ad_suitability=ad_suitability,
            made_for_kids=status.get("madeForKids", False),
            content_rating_flags=rating_flags,
            failure_reason=status.get("failureReason"),
            rejection_reason=status.get("rejectionReason"),
        )

    # ------------------------------------------------------------------

    async def get_video_statistics(
        self,
        video_ids: list[str],
        channel_id: uuid.UUID,
    ) -> list[VideoStats]:
        """Batch-fetch statistics for up to 50 videos.  Cost: 1 quota unit.

        This is the near-real-time monitoring endpoint.
        """
        if not video_ids:
            return []

        # YouTube allows max 50 IDs per call
        results: list[VideoStats] = []
        for batch_start in range(0, len(video_ids), 50):
            batch = video_ids[batch_start : batch_start + 50]
            resp = await self._api_request(
                "GET",
                f"{YOUTUBE_API_BASE}/videos",
                channel_id=channel_id,
                params={"part": "statistics", "id": ",".join(batch)},
            )
            resp.raise_for_status()
            data = resp.json()

            for item in data.get("items", []):
                stats = item.get("statistics", {})
                results.append(
                    VideoStats(
                        youtube_video_id=item["id"],
                        view_count=int(stats.get("viewCount", 0)),
                        like_count=int(stats.get("likeCount", 0)),
                        comment_count=int(stats.get("commentCount", 0)),
                        favorite_count=int(stats.get("favoriteCount", 0)),
                    )
                )

        return results

    # ==================================================================
    # OAuth2 token management
    # ==================================================================

    async def _get_access_token(self, channel_id: uuid.UUID) -> str:
        """Return a valid access token, refreshing if needed.

        Flow:
        1. Check in-memory cache for a token that won't expire for 5+ min.
        2. If stale or missing, fetch the refresh token from
           ``channel_credentials`` via Supabase REST API.
        3. Exchange the refresh token for a new access token via Google
           OAuth2.
        4. Cache the new token for ~55 minutes.
        """
        return await self._refresh_access_token_if_needed(channel_id)

    async def _refresh_access_token_if_needed(
        self,
        channel_id: uuid.UUID,
    ) -> str:
        """Return a cached token or transparently refresh it."""
        cached = self._token_cache.get(channel_id)
        if cached is not None:
            token, expires_at = cached
            if time.monotonic() < expires_at - TOKEN_REFRESH_BUFFER_SECONDS:
                return token

        refresh_token = await self._fetch_refresh_token(channel_id)
        access_token, expires_in = await self._exchange_refresh_token(refresh_token)

        self._token_cache[channel_id] = (
            access_token,
            time.monotonic() + expires_in,
        )

        await logger.ainfo(
            "oauth_token_refreshed",
            channel_id=str(channel_id),
            expires_in=expires_in,
        )
        return access_token

    async def _fetch_refresh_token(self, channel_id: uuid.UUID) -> str:
        """Retrieve the YouTube OAuth refresh token from ``channel_credentials``.

        Uses the Supabase PostgREST API with the service-role key (bypasses
        RLS).  The column ``youtube_oauth_refresh_token_encrypted`` may be
        application-level encrypted — a decryption layer should be added when
        the encryption scheme is finalised.
        """
        supabase_url = self._settings.database.url
        service_key = self._settings.database.service_role_key

        resp = await self._http.get(
            f"{supabase_url}/rest/v1/channel_credentials",
            params={
                "select": "youtube_oauth_refresh_token_encrypted",
                "channel_id": f"eq.{channel_id}",
            },
            headers={
                "apikey": service_key,
                "Authorization": f"Bearer {service_key}",
            },
            timeout=10.0,
        )
        resp.raise_for_status()
        rows = resp.json()

        if not rows:
            raise YouTubeUploadError(f"No credentials row found for channel {channel_id}")

        token: str | None = rows[0].get("youtube_oauth_refresh_token_encrypted")
        if not token:
            raise YouTubeUploadError(f"YouTube refresh token is empty for channel {channel_id}")

        return token

    async def _exchange_refresh_token(
        self,
        refresh_token: str,
    ) -> tuple[str, int]:
        """Exchange a refresh token for a short-lived access token.

        POST ``https://oauth2.googleapis.com/token``

        Returns
        -------
        tuple[str, int]
            ``(access_token, expires_in_seconds)``
        """
        resp = await self._http.post(
            OAUTH_TOKEN_URL,
            data={
                "client_id": self._settings.youtube.client_id,
                "client_secret": self._settings.youtube.client_secret,
                "refresh_token": refresh_token,
                "grant_type": "refresh_token",
            },
            timeout=15.0,
        )

        if resp.status_code == 400:
            body = resp.json()
            error = body.get("error", "")
            if error == "invalid_grant":
                raise YouTubeUploadError(
                    "Refresh token revoked or expired — re-authenticate the "
                    "channel in the CrimeMill dashboard."
                )
            raise YouTubeUploadError(f"OAuth token exchange failed: {body}")

        resp.raise_for_status()
        data = resp.json()
        return data["access_token"], int(data.get("expires_in", 3600))

    # ==================================================================
    # Resumable upload internals
    # ==================================================================

    async def _initiate_resumable_upload(
        self,
        access_token: str,
        metadata: dict[str, Any],
        file_path: str,
    ) -> str:
        """POST to YouTube's resumable-upload endpoint.

        Returns the upload URI (``Location`` header) that subsequent PUT
        requests will target.  The URI embeds its own auth — PUT requests
        do **not** require an ``Authorization`` header.
        """
        file_size = Path(file_path).stat().st_size

        resp = await self._http.post(
            f"{YOUTUBE_UPLOAD_BASE}/videos",
            params={
                "uploadType": "resumable",
                "part": "snippet,status",
            },
            headers={
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json; charset=UTF-8",
                "X-Upload-Content-Length": str(file_size),
                "X-Upload-Content-Type": "video/mp4",
            },
            json=metadata,
            timeout=API_TIMEOUT,
        )

        if resp.status_code == 403:
            body = resp.json()
            errors = body.get("error", {}).get("errors", [])
            for err in errors:
                if err.get("reason") == "quotaExceeded":
                    raise QuotaExceededError("YouTube API daily quota exceeded")
            raise YouTubeUploadError(f"Forbidden when initiating upload: {resp.text}")

        resp.raise_for_status()

        upload_uri: str | None = resp.headers.get("location")
        if not upload_uri:
            raise YouTubeUploadError("No Location header in resumable-upload init response")

        await logger.ainfo(
            "resumable_upload_initiated",
            file_size=file_size,
        )
        return upload_uri

    async def _upload_file_resumable(
        self,
        upload_uri: str,
        file_path: str,
    ) -> str:
        """Upload the video file in 10 MB chunks via the resumable protocol.

        Handles:
        - ``308 Resume Incomplete`` — continue from the committed byte
        - ``5xx`` — retry with exponential backoff (max 10 retries)
        - ``404`` — session expired; raises ``UploadSessionExpiredError``
        - Other ``4xx`` — non-retryable, raises immediately

        Returns the YouTube video ID from the final ``200``/``201`` response.
        """
        file_size = Path(file_path).stat().st_size
        offset = 0
        retries = 0

        with open(file_path, "rb") as f:
            while offset < file_size:
                f.seek(offset)
                remaining = file_size - offset
                chunk_size = min(CHUNK_SIZE, remaining)
                chunk = f.read(chunk_size)
                end = offset + len(chunk) - 1

                content_range = f"bytes {offset}-{end}/{file_size}"

                try:
                    resp = await self._http.put(
                        upload_uri,
                        content=chunk,
                        headers={
                            "Content-Length": str(len(chunk)),
                            "Content-Range": content_range,
                            "Content-Type": "video/mp4",
                        },
                        timeout=httpx.Timeout(
                            connect=30.0,
                            read=UPLOAD_TIMEOUT,
                            write=UPLOAD_TIMEOUT,
                            pool=30.0,
                        ),
                    )
                except (
                    httpx.ConnectError,
                    httpx.ReadTimeout,
                    httpx.WriteTimeout,
                    ConnectionError,
                    TimeoutError,
                ) as exc:
                    retries += 1
                    if retries > MAX_UPLOAD_RETRIES:
                        raise YouTubeUploadError(
                            f"Upload network error after {MAX_UPLOAD_RETRIES} retries: {exc}"
                        ) from exc

                    delay = min(
                        (2**retries) * random.random(),
                        RETRY_CAP_SECONDS,
                    )
                    await logger.awarning(
                        "upload_chunk_network_error",
                        offset=offset,
                        retry=retries,
                        delay=round(delay, 2),
                        error=str(exc),
                    )
                    await asyncio.sleep(delay)

                    # Re-sync offset with what YouTube actually committed
                    offset = await self._query_upload_progress(
                        upload_uri,
                        file_size,
                    )
                    continue

                # --- Successful HTTP response ---

                if resp.status_code in (200, 201):
                    retries = 0
                    data = resp.json()
                    video_id: str = data["id"]
                    await logger.ainfo(
                        "upload_complete_chunk",
                        youtube_video_id=video_id,
                        total_bytes=file_size,
                    )
                    return video_id

                if resp.status_code == 308:
                    # Resume Incomplete — extract committed range
                    retries = 0
                    range_header = resp.headers.get("range")
                    if range_header:
                        # "bytes=0-1234567" → committed through byte 1234567
                        committed = int(range_header.rsplit("-", 1)[1]) + 1
                        offset = committed
                    else:
                        # No Range header = no bytes committed yet
                        offset += len(chunk)

                    pct = round(offset / file_size * 100, 1)
                    await logger.ainfo(
                        "upload_chunk_committed",
                        offset=offset,
                        total=file_size,
                        percent=pct,
                    )
                    continue

                if resp.status_code == 404:
                    raise UploadSessionExpiredError(
                        "Upload session expired (404 on PUT). Must restart."
                    )

                if resp.status_code >= 500:
                    retries += 1
                    if retries > MAX_UPLOAD_RETRIES:
                        raise YouTubeUploadError(
                            f"YouTube server error {resp.status_code} after "
                            f"{MAX_UPLOAD_RETRIES} retries: {resp.text[:200]}"
                        )

                    delay = min(
                        (2**retries) * random.random(),
                        RETRY_CAP_SECONDS,
                    )
                    await logger.awarning(
                        "upload_chunk_server_error",
                        status=resp.status_code,
                        retry=retries,
                        delay=round(delay, 2),
                    )
                    await asyncio.sleep(delay)

                    offset = await self._query_upload_progress(
                        upload_uri,
                        file_size,
                    )
                    continue

                # Non-retryable 4xx
                raise YouTubeUploadError(
                    f"Non-retryable error {resp.status_code} during upload: {resp.text[:300]}"
                )

        raise YouTubeUploadError("Upload loop finished without receiving a video ID")

    async def _query_upload_progress(
        self,
        upload_uri: str,
        file_size: int,
    ) -> int:
        """Query the upload URI for committed bytes.

        Sends ``Content-Range: bytes */{total}`` with an empty body.
        Returns the byte offset to resume from.
        """
        try:
            resp = await self._http.put(
                upload_uri,
                content=b"",
                headers={
                    "Content-Length": "0",
                    "Content-Range": f"bytes */{file_size}",
                },
                timeout=30.0,
            )
        except (httpx.ConnectError, httpx.ReadTimeout, TimeoutError):
            await logger.awarning("upload_progress_query_failed")
            return 0

        if resp.status_code == 308:
            range_header = resp.headers.get("range")
            if range_header:
                return int(range_header.rsplit("-", 1)[1]) + 1
            return 0

        if resp.status_code in (200, 201):
            # Upload was already complete
            return file_size

        if resp.status_code == 404:
            raise UploadSessionExpiredError("Upload session expired during progress query")

        return 0

    # ==================================================================
    # General YouTube API helper
    # ==================================================================

    async def _api_request(
        self,
        method: str,
        url: str,
        *,
        channel_id: uuid.UUID,
        headers: dict[str, str] | None = None,
        timeout: float = API_TIMEOUT,
        **kwargs: Any,
    ) -> httpx.Response:
        """Make an authenticated YouTube API request with retry.

        Automatically refreshes the OAuth token on 401 and retries on
        5xx/network errors up to ``MAX_API_RETRIES`` times.
        """
        merged_headers = dict(headers) if headers else {}
        last_exc: BaseException | None = None

        for attempt in range(MAX_API_RETRIES):
            token = await self._refresh_access_token_if_needed(channel_id)
            merged_headers["Authorization"] = f"Bearer {token}"

            try:
                resp = await self._http.request(
                    method,
                    url,
                    headers=merged_headers,
                    timeout=timeout,
                    **kwargs,
                )
            except (
                httpx.ConnectError,
                httpx.ReadTimeout,
                ConnectionError,
                TimeoutError,
            ) as exc:
                last_exc = exc
                if attempt < MAX_API_RETRIES - 1:
                    delay = min(
                        (2**attempt) * random.random(),
                        RETRY_CAP_SECONDS,
                    )
                    await logger.awarning(
                        "api_network_error",
                        method=method,
                        url=url,
                        attempt=attempt + 1,
                        delay=round(delay, 2),
                        error=str(exc),
                    )
                    await asyncio.sleep(delay)
                    continue
                raise YouTubeUploadError(
                    f"Network error after {MAX_API_RETRIES} retries: {exc}"
                ) from exc

            # 401 → token might be stale; evict cache and retry once
            if resp.status_code == 401:
                self._token_cache.pop(channel_id, None)
                if attempt < MAX_API_RETRIES - 1:
                    await logger.awarning(
                        "api_401_refreshing_token",
                        method=method,
                        url=url,
                    )
                    continue
                raise YouTubeUploadError(f"Unauthorized after token refresh: {resp.text[:200]}")

            # 403 quota check
            if resp.status_code == 403:
                body = resp.json()
                for err in body.get("error", {}).get("errors", []):
                    if err.get("reason") == "quotaExceeded":
                        raise QuotaExceededError("YouTube API daily quota exceeded")

            # 5xx → retry
            if resp.status_code >= 500:
                last_exc = httpx.HTTPStatusError(
                    f"Server error {resp.status_code}",
                    request=resp.request,
                    response=resp,
                )
                if attempt < MAX_API_RETRIES - 1:
                    delay = min(
                        (2**attempt) * random.random(),
                        RETRY_CAP_SECONDS,
                    )
                    await logger.awarning(
                        "api_server_error",
                        status=resp.status_code,
                        attempt=attempt + 1,
                        delay=round(delay, 2),
                    )
                    await asyncio.sleep(delay)
                    continue

            return resp

        # Should not be reached, but satisfy the type checker
        if last_exc is not None:
            raise YouTubeUploadError(f"API request failed after retries: {last_exc}") from last_exc
        raise YouTubeUploadError("API request retry loop exited unexpectedly")

    # ==================================================================
    # Upload-flow helpers
    # ==================================================================

    async def _poll_processing(
        self,
        youtube_video_id: str,
        channel_id: uuid.UUID,
    ) -> tuple[str, int]:
        """Poll until YouTube finishes processing.

        Returns ``(ad_suitability, total_quota_used_for_polls)``.
        """
        deadline = time.monotonic() + POLL_TIMEOUT_SECONDS
        polls = 0

        while time.monotonic() < deadline:
            status = await self.get_video_status(youtube_video_id, channel_id)
            polls += 1

            if status.upload_status == "processed":
                return status.ad_suitability, polls * QUOTA_VIDEO_LIST

            if status.upload_status in ("failed", "rejected", "deleted"):
                reason = status.failure_reason or status.rejection_reason or "unknown"
                if status.upload_status == "rejected":
                    raise ContentFilteredError(f"Video rejected by YouTube: {reason}")
                raise YouTubeUploadError(f"Video processing {status.upload_status}: {reason}")

            # Still "uploaded" — gray clock icon — keep waiting
            await logger.ainfo(
                "poll_processing_waiting",
                youtube_video_id=youtube_video_id,
                upload_status=status.upload_status,
                polls=polls,
            )
            await asyncio.sleep(POLL_INTERVAL_SECONDS)

        raise YouTubeUploadError(
            f"Video processing timed out after {POLL_TIMEOUT_SECONDS // 60} minutes ({polls} polls)"
        )

    async def _check_content_id_claims(
        self,
        youtube_video_id: str,
        channel_id: uuid.UUID,
    ) -> list[dict[str, object]]:
        """Check for Content ID claims via ``contentDetails.contentRating``.

        The YouTube Data API does not directly expose Content ID claims
        (that requires YouTube Content ID API or Studio).  We approximate
        by checking ``contentDetails.contentRating`` for restrictive flags
        and ``status.license`` anomalies.

        Returns a list of claim-like dicts (empty list = no issues detected).
        """
        resp = await self._api_request(
            "GET",
            f"{YOUTUBE_API_BASE}/videos",
            channel_id=channel_id,
            params={
                "part": "contentDetails,status",
                "id": youtube_video_id,
            },
        )
        resp.raise_for_status()
        data = resp.json()

        if not data.get("items"):
            return []

        item = data["items"][0]
        content_rating = item.get("contentDetails", {}).get(
            "contentRating",
            {},
        )
        claims: list[dict[str, object]] = []

        for system, rating in content_rating.items():
            claims.append(
                {
                    "type": "content_rating",
                    "system": system,
                    "rating": rating,
                    "source": "youtube_data_api",
                }
            )

        if claims:
            await logger.awarning(
                "content_rating_flags_detected",
                youtube_video_id=youtube_video_id,
                flags=claims,
            )

        return claims

    async def _update_video_status(
        self,
        youtube_video_id: str,
        channel_id: uuid.UUID,
        *,
        privacy_status: str,
        publish_at: str | None = None,
    ) -> None:
        """PATCH ``videos.update`` to change privacy or schedule publish."""
        body: dict[str, Any] = {
            "id": youtube_video_id,
            "status": {
                "privacyStatus": privacy_status,
            },
        }

        if publish_at and privacy_status == "private":
            body["status"]["publishAt"] = publish_at

        resp = await self._api_request(
            "PUT",
            f"{YOUTUBE_API_BASE}/videos",
            channel_id=channel_id,
            params={"part": "status"},
            json=body,
        )
        resp.raise_for_status()

        await logger.ainfo(
            "video_status_updated",
            youtube_video_id=youtube_video_id,
            privacy_status=privacy_status,
            publish_at=publish_at,
        )


# ==================================================================
# Module-level helpers
# ==================================================================


def _build_upload_metadata(video: VideoUploadInput) -> dict[str, Any]:
    """Build the JSON metadata body for the resumable upload initiation.

    Enforces YouTube field limits and sets the mandatory
    ``containsSyntheticMedia=true`` flag.
    """
    # Enforce byte limits
    description = video.description
    if len(description.encode("utf-8")) > MAX_DESCRIPTION_BYTES:
        description = description.encode("utf-8")[:MAX_DESCRIPTION_BYTES].decode(
            "utf-8", errors="ignore"
        )

    # Enforce tag character limit (sum of all tags ≤ 500 chars)
    tags: list[str] = []
    char_total = 0
    for tag in video.tags:
        tag_len = len(tag)
        if char_total + tag_len > MAX_TAGS_CHARS:
            break
        tags.append(tag)
        char_total += tag_len

    metadata: dict[str, Any] = {
        "snippet": {
            "title": video.title[:100],
            "description": description,
            "tags": tags,
            "categoryId": str(video.category_id),
            "defaultLanguage": "en",
        },
        "status": {
            "privacyStatus": "private",
            "selfDeclaredMadeForKids": False,
            # ALWAYS true — non-negotiable for AI-generated content
            "containsSyntheticMedia": True,
        },
    }

    if video.scheduled_publish_at:
        metadata["status"]["publishAt"] = video.scheduled_publish_at.isoformat()

    return metadata


def _json_dumps(obj: Any) -> str:
    """Compact JSON serialization for multipart bodies."""
    import json

    return json.dumps(obj, separators=(",", ":"))
