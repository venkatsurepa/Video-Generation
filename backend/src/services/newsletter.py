"""Newsletter manager — email notifications for new videos and weekly digests.

Uses Resend (https://resend.com) as the transactional email provider.
Free tier: 3,000 emails/month, sufficient for early growth.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any

import structlog

from src.utils.retry import async_retry

if TYPE_CHECKING:
    import uuid

    import httpx

    from src.config import Settings

logger = structlog.get_logger()

_RESEND_API_URL = "https://api.resend.com/emails"

# ---------------------------------------------------------------------------
# SQL queries (newsletter-specific)
# ---------------------------------------------------------------------------

_GET_VIDEO_FOR_EMAIL = """
SELECT
    v.id, v.title, v.youtube_video_id, v.channel_id,
    c.name AS channel_name, c.handle AS channel_handle
FROM videos v
JOIN channels c ON c.id = v.channel_id
WHERE v.id = %(video_id)s;
"""

_GET_WEEKLY_VIDEOS = """
SELECT
    v.id, v.title, v.youtube_video_id, v.published_at,
    c.name AS channel_name
FROM videos v
JOIN channels c ON c.id = v.channel_id
WHERE v.channel_id = %(channel_id)s
  AND v.status = 'published'
  AND v.published_at >= %(since)s
ORDER BY v.published_at DESC;
"""


class NewsletterManager:
    """Sends email notifications for new videos and weekly digests.

    Email list built via YouTube description link + channel page.
    All emails include CAN-SPAM compliant unsubscribe link.
    """

    def __init__(
        self,
        settings: Settings,
        http_client: httpx.AsyncClient,
    ) -> None:
        self._settings = settings
        self._http = http_client

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @async_retry(max_attempts=2, base_delay=2.0)
    async def send_new_video_alert(
        self,
        video_id: uuid.UUID,
        subscriber_list_id: str,
        *,
        db_pool: Any = None,
    ) -> None:
        """Send email notification for new video publication.

        Email content:
        - Subject: "[Channel] New Investigation: {title}"
        - Body: case hook (2-3 sentences), video thumbnail, watch link
        - Unsubscribe link (CAN-SPAM compliance)
        """
        if not self._settings.newsletter.resend_api_key:
            await logger.awarning("newsletter_skipped", reason="RESEND_API_KEY not set")
            return

        # Fetch video info
        if db_pool is None:
            raise ValueError("db_pool required for send_new_video_alert")

        async with db_pool.connection() as conn:
            cur = await conn.execute(_GET_VIDEO_FOR_EMAIL, {"video_id": video_id})
            row = await cur.fetchone()

        if row is None:
            raise ValueError(f"Video {video_id} not found")

        channel_name = row["channel_name"]
        title = row["title"] or "New Investigation"
        yt_id = row["youtube_video_id"] or ""
        watch_url = f"https://youtube.com/watch?v={yt_id}" if yt_id else ""
        thumbnail_url = f"https://img.youtube.com/vi/{yt_id}/maxresdefault.jpg" if yt_id else ""

        subject = f"[{channel_name}] New Investigation: {title}"
        html_body = _build_video_alert_html(
            channel_name=channel_name,
            title=title,
            watch_url=watch_url,
            thumbnail_url=thumbnail_url,
        )

        await self._send_email(
            to=subscriber_list_id,  # Resend audience ID
            subject=subject,
            html=html_body,
        )

        await logger.ainfo(
            "video_alert_sent",
            video_id=str(video_id),
            channel=channel_name,
        )

    @async_retry(max_attempts=2, base_delay=2.0)
    async def send_weekly_digest(
        self,
        channel_id: uuid.UUID,
        *,
        subscriber_list_id: str = "",
        db_pool: Any = None,
    ) -> None:
        """Weekly email with all videos from the past week.

        Builds habit and drives returning viewers (strong algorithm signal).
        """
        if not self._settings.newsletter.resend_api_key:
            await logger.awarning("digest_skipped", reason="RESEND_API_KEY not set")
            return

        if db_pool is None:
            raise ValueError("db_pool required for send_weekly_digest")

        since = datetime.utcnow() - timedelta(days=7)

        async with db_pool.connection() as conn:
            cur = await conn.execute(
                _GET_WEEKLY_VIDEOS,
                {"channel_id": channel_id, "since": since},
            )
            rows = await cur.fetchall()

        if not rows:
            await logger.ainfo("digest_skipped_no_videos", channel_id=str(channel_id))
            return

        channel_name = rows[0]["channel_name"]

        subject = f"[{channel_name}] This Week's Investigations"
        html_body = _build_digest_html(channel_name, rows)

        to = subscriber_list_id or self._settings.newsletter.from_email
        await self._send_email(to=to, subject=subject, html=html_body)

        await logger.ainfo(
            "weekly_digest_sent",
            channel_id=str(channel_id),
            video_count=len(rows),
        )

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    async def _send_email(
        self,
        to: str,
        subject: str,
        html: str,
    ) -> dict[str, Any]:
        """Send an email via Resend API."""
        resp = await self._http.post(
            _RESEND_API_URL,
            headers={
                "Authorization": f"Bearer {self._settings.newsletter.resend_api_key}",
                "Content-Type": "application/json",
            },
            json={
                "from": self._settings.newsletter.from_email,
                "to": [to],
                "subject": subject,
                "html": html,
            },
            timeout=15.0,
        )
        resp.raise_for_status()
        result: dict[str, Any] = resp.json()
        return result


# ---------------------------------------------------------------------------
# Email HTML templates
# ---------------------------------------------------------------------------


def _build_video_alert_html(
    channel_name: str,
    title: str,
    watch_url: str,
    thumbnail_url: str,
) -> str:
    """Build HTML for new video alert email."""
    return f"""\
<!DOCTYPE html>
<html>
<head><meta charset="utf-8"></head>
<body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
             max-width: 600px; margin: 0 auto; padding: 20px; background: #0a0a0a; color: #e0e0e0;">
  <div style="text-align: center; padding: 20px 0;">
    <h2 style="color: #ff3333; margin: 0;">{channel_name}</h2>
    <p style="color: #888; font-size: 14px;">New Investigation</p>
  </div>

  <div style="background: #1a1a1a; border-radius: 8px; overflow: hidden; margin: 20px 0;">
    {
        "<a href='" + watch_url + "'><img src='" + thumbnail_url + "' "
        "style='width: 100%; display: block;' alt='Video thumbnail'></a>"
        if thumbnail_url
        else ""
    }
    <div style="padding: 20px;">
      <h3 style="margin: 0 0 10px; color: #fff;">{title}</h3>
      <p style="color: #aaa; font-size: 14px; line-height: 1.5;">
        A new investigation just dropped. Click below to watch now.
      </p>
      {
        "<a href='" + watch_url + "' "
        "style='display: inline-block; background: #ff3333; color: white; "
        "padding: 12px 24px; text-decoration: none; border-radius: 4px; "
        "font-weight: bold; margin-top: 10px;'>Watch Now</a>"
        if watch_url
        else ""
    }
    </div>
  </div>

  <div style="text-align: center; padding: 20px; color: #666; font-size: 12px;">
    <p>You received this because you subscribed to {channel_name} updates.</p>
    <p><a href="{{{{UNSUBSCRIBE_URL}}}}" style="color: #888;">Unsubscribe</a></p>
  </div>
</body>
</html>"""


def _build_digest_html(channel_name: str, videos: list[dict[str, Any]]) -> str:
    """Build HTML for weekly digest email."""
    video_items = ""
    for v in videos:
        yt_id = v.get("youtube_video_id", "")
        url = f"https://youtube.com/watch?v={yt_id}" if yt_id else "#"
        thumb = f"https://img.youtube.com/vi/{yt_id}/mqdefault.jpg" if yt_id else ""
        title = v.get("title", "Untitled")

        video_items += f"""\
    <tr>
      <td style="padding: 10px;">
        {
            "<a href='" + url + "'><img src='" + thumb + "' "
            "style='width: 120px; border-radius: 4px;' alt=''></a>"
            if thumb
            else ""
        }
      </td>
      <td style="padding: 10px; vertical-align: top;">
        <a href="{url}" style="color: #ff3333; text-decoration: none; font-weight: bold;">
          {title}
        </a>
      </td>
    </tr>
"""

    return f"""\
<!DOCTYPE html>
<html>
<head><meta charset="utf-8"></head>
<body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
             max-width: 600px; margin: 0 auto; padding: 20px; background: #0a0a0a; color: #e0e0e0;">
  <div style="text-align: center; padding: 20px 0;">
    <h2 style="color: #ff3333; margin: 0;">{channel_name}</h2>
    <p style="color: #888; font-size: 14px;">This Week's Investigations</p>
  </div>

  <div style="background: #1a1a1a; border-radius: 8px; padding: 20px; margin: 20px 0;">
    <table cellspacing="0" cellpadding="0" style="width: 100%;">
      {video_items}
    </table>
  </div>

  <div style="text-align: center; padding: 20px; color: #666; font-size: 12px;">
    <p>You received this because you subscribed to {channel_name} updates.</p>
    <p><a href="{{{{UNSUBSCRIBE_URL}}}}" style="color: #888;">Unsubscribe</a></p>
  </div>
</body>
</html>"""
