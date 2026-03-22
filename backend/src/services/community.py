"""Community ecosystem service — Discord, Patreon, and topic submissions.

Manages community engagement across Discord (notifications, discussion threads),
Patreon (member sync, early access, patron credits), and topic submissions
(Google Forms, Discord, manual).  True crime has the highest Patreon conversion
rate (1.2-2.5%), so the early-access perk is prioritised.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING, Any, cast

import structlog

from src.db import queries
from src.models.community import (
    CommunityMetrics,
    DiscordNotification,
    PatreonSyncResult,
    TopicSubmission,
    TopicSubmissionCreate,
)

if TYPE_CHECKING:
    import uuid

    import httpx
    from psycopg_pool import AsyncConnectionPool

    from src.config import Settings

logger = structlog.get_logger()

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DISCORD_API_BASE = "https://discord.com/api/v10"
PATREON_API_BASE = "https://www.patreon.com/api/oauth2/v2"
GOOGLE_SHEETS_API = "https://sheets.googleapis.com/v4/spreadsheets"


class CommunityManager:
    """Manages community integrations: Discord, Patreon, topic submissions."""

    def __init__(
        self,
        settings: Settings,
        http_client: httpx.AsyncClient,
        db_pool: AsyncConnectionPool,
    ) -> None:
        self._settings = settings
        self._http = http_client
        self._pool = db_pool

    # ------------------------------------------------------------------
    # Discord notifications
    # ------------------------------------------------------------------

    async def notify_discord_new_video(
        self,
        video_id: uuid.UUID,
        title: str,
        description: str,
        youtube_video_id: str,
        thumbnail_url: str = "",
        duration_seconds: int = 0,
        category: str = "",
    ) -> DiscordNotification:
        """Post to Discord when a new video publishes.

        Sends a rich embed to the configured webhook URL with video details,
        thumbnail, and a link.  Also posts a spoiler-tagged message in the
        case-discussion channel for viewers who haven't watched yet.
        """
        webhook_url = self._settings.discord.webhook_url
        if not webhook_url:
            return DiscordNotification(
                video_id=video_id,
                notification_type="new_video",
                webhook_url="",
                success=False,
                error="DISCORD_WEBHOOK_URL not configured",
            )

        youtube_url = f"https://youtube.com/watch?v={youtube_video_id}"
        duration_str = f"{duration_seconds // 60} min" if duration_seconds else "—"

        embed: dict[str, Any] = {
            "title": title,
            "description": (description[:200] + "...") if len(description) > 200 else description,
            "url": youtube_url,
            "color": 0xCC0000,  # crime red
            "fields": [
                {"name": "Duration", "value": duration_str, "inline": True},
                {"name": "Category", "value": category or "True Crime", "inline": True},
            ],
            "footer": {"text": "CrimeMill \u2022 Financial Crime Documentaries"},
        }
        if thumbnail_url:
            embed["image"] = {"url": thumbnail_url}

        payload = {
            "content": "\U0001f534 **NEW VIDEO** \U0001f534",
            "embeds": [embed],
        }

        message_id = ""
        error = ""
        success = True
        try:
            resp = await self._http.post(webhook_url + "?wait=true", json=payload)
            resp.raise_for_status()
            data = resp.json()
            message_id = str(data.get("id", ""))
        except Exception as exc:
            error = str(exc)
            success = False
            await logger.awarning("discord_new_video_failed", error=error, video_id=str(video_id))

        # Post spoiler-tagged version in case-discussion channel
        if success and self._settings.discord.bot_token:
            channel_id = self._settings.discord.case_discussion_channel_id
            if channel_id:
                spoiler_payload = {
                    "content": (
                        f"\U0001f4e2 New case dropped: **{title}**\n"
                        f"||{description[:300]}||\n"
                        f"Watch: {youtube_url}"
                    ),
                }
                try:
                    await self._http.post(
                        f"{DISCORD_API_BASE}/channels/{channel_id}/messages",
                        json=spoiler_payload,
                        headers={"Authorization": f"Bot {self._settings.discord.bot_token}"},
                    )
                except Exception as exc:
                    await logger.awarning("discord_spoiler_post_failed", error=str(exc))

        await logger.ainfo(
            "discord_new_video_notified",
            video_id=str(video_id),
            success=success,
            message_id=message_id,
        )

        return DiscordNotification(
            video_id=video_id,
            notification_type="new_video",
            webhook_url=webhook_url,
            message_id=message_id,
            success=success,
            error=error,
        )

    async def notify_discord_upcoming(
        self,
        video_id: uuid.UUID,
        title: str,
        publish_at: datetime,
    ) -> DiscordNotification:
        """Post 24-hour advance notice for an upcoming video."""
        webhook_url = self._settings.discord.webhook_url
        if not webhook_url:
            return DiscordNotification(
                video_id=video_id,
                notification_type="upcoming",
                webhook_url="",
                success=False,
                error="DISCORD_WEBHOOK_URL not configured",
            )

        time_str = publish_at.strftime("%B %d at %I:%M %p UTC")
        payload = {
            "content": f"\U0001f4e2 Tomorrow at {time_str}: **{title}** \u2014 Set your reminder!",
            "embeds": [
                {
                    "title": f"\U0001f550 Upcoming: {title}",
                    "description": f"Premiering {time_str}",
                    "color": 0xFFAA00,
                }
            ],
        }

        message_id = ""
        error = ""
        success = True
        try:
            resp = await self._http.post(webhook_url + "?wait=true", json=payload)
            resp.raise_for_status()
            data = resp.json()
            message_id = str(data.get("id", ""))
        except Exception as exc:
            error = str(exc)
            success = False
            await logger.awarning("discord_upcoming_failed", error=error)

        return DiscordNotification(
            video_id=video_id,
            notification_type="upcoming",
            webhook_url=webhook_url,
            message_id=message_id,
            success=success,
            error=error,
        )

    async def create_case_discussion_thread(
        self,
        video_id: uuid.UUID,
        case_name: str,
    ) -> str:
        """Create a Discord thread for case discussion after video publishes.

        Uses the Discord API to create a thread in the case-discussion channel.
        Auto-archives after 7 days (10080 minutes).
        """
        bot_token = self._settings.discord.bot_token
        channel_id = self._settings.discord.case_discussion_channel_id
        if not bot_token or not channel_id:
            await logger.awarning(
                "discord_thread_skipped", reason="bot_token or channel_id missing"
            )
            return ""

        headers = {"Authorization": f"Bot {bot_token}"}
        payload = {
            "name": f"\U0001f4ac Discussion: {case_name}"[:100],  # Discord 100-char limit
            "auto_archive_duration": 10080,  # 7 days
            "type": 11,  # PUBLIC_THREAD
        }

        try:
            resp = await self._http.post(
                f"{DISCORD_API_BASE}/channels/{channel_id}/threads",
                json=payload,
                headers=headers,
            )
            resp.raise_for_status()
            thread_data = resp.json()
            thread_id = str(thread_data.get("id", ""))

            await logger.ainfo(
                "discord_thread_created",
                video_id=str(video_id),
                thread_id=thread_id,
                case_name=case_name,
            )
            return thread_id
        except Exception as exc:
            await logger.awarning("discord_thread_failed", error=str(exc))
            return ""

    # ------------------------------------------------------------------
    # Patreon integration
    # ------------------------------------------------------------------

    async def sync_patreon_members(self) -> PatreonSyncResult:
        """Sync Patreon membership data via API v2.

        True crime has 1.2-2.5% Patreon conversion rate.  Syncs the member
        list to the local DB for early access scheduling, patron credits,
        Discord role assignment, and exclusive content access.
        """
        campaign_id = self._settings.patreon.campaign_id
        access_token = self._settings.patreon.access_token
        if not campaign_id or not access_token:
            await logger.awarning(
                "patreon_sync_skipped", reason="campaign_id or access_token missing"
            )
            return PatreonSyncResult()

        headers = {"Authorization": f"Bearer {access_token}"}
        new_count = 0
        updated_count = 0
        synced_ids: set[str] = set()

        # Paginate through all members
        url: str | None = (
            f"{PATREON_API_BASE}/campaigns/{campaign_id}/members"
            "?include=currently_entitled_tiers"
            "&fields%5Bmember%5D=full_name,email,patron_status"
            "&fields%5Btier%5D=title,amount_cents"
        )

        while url:
            try:
                resp = await self._http.get(url, headers=headers)
                resp.raise_for_status()
                data = resp.json()
            except Exception as exc:
                await logger.awarning("patreon_api_error", error=str(exc))
                break

            # Build tier lookup from included data
            tier_lookup: dict[str, dict[str, Any]] = {}
            for inc in data.get("included", []):
                if inc.get("type") == "tier":
                    tier_lookup[inc["id"]] = {
                        "name": inc.get("attributes", {}).get("title", ""),
                        "amount_cents": inc.get("attributes", {}).get("amount_cents", 0),
                    }

            for member in data.get("data", []):
                attrs = member.get("attributes", {})
                patreon_id = member.get("id", "")
                is_active = attrs.get("patron_status") == "active_patron"

                # Resolve tier
                tier_rel = (
                    member.get("relationships", {})
                    .get("currently_entitled_tiers", {})
                    .get("data", [])
                )
                tier_info = tier_lookup.get(tier_rel[0]["id"], {}) if tier_rel else {}

                async with self._pool.connection() as conn:
                    row = await (
                        await conn.execute(
                            queries.UPSERT_PATREON_MEMBER,
                            {
                                "patreon_id": patreon_id,
                                "name": attrs.get("full_name", ""),
                                "email": attrs.get("email", ""),
                                "tier_name": tier_info.get("name", ""),
                                "tier_amount_cents": tier_info.get("amount_cents", 0),
                                "is_active": is_active,
                            },
                        )
                    ).fetchone()

                    if row:
                        r = cast("dict[str, Any]", row)
                        if r.get("created_at") == r.get("last_synced_at"):
                            new_count += 1
                        else:
                            updated_count += 1

                synced_ids.add(patreon_id)

            # Next page
            url = data.get("links", {}).get("next")

        # Mark members not seen in this sync as churned
        churned_count = 0
        if synced_ids:
            cutoff = datetime.now(UTC) - timedelta(minutes=5)
            async with self._pool.connection() as conn:
                churned_rows = await (
                    await conn.execute(
                        queries.MARK_CHURNED_PATRONS,
                        {"cutoff": cutoff},
                    )
                ).fetchall()
                churned_count = len(churned_rows)

        # Calculate MRR
        async with self._pool.connection() as conn:
            mrr_row_raw = await (await conn.execute(queries.COUNT_ACTIVE_PATRONS)).fetchone()

        mrr_row = cast("dict[str, Any]", mrr_row_raw) if mrr_row_raw else None
        total_mrr = mrr_row["total_mrr_cents"] if mrr_row else 0
        total_patrons = mrr_row["patron_count"] if mrr_row else 0

        result = PatreonSyncResult(
            total_members=total_patrons,
            new_members=new_count,
            updated_members=updated_count,
            churned_members=churned_count,
            total_mrr_cents=total_mrr,
        )

        await logger.ainfo(
            "patreon_sync_complete",
            total=result.total_members,
            new=result.new_members,
            churned=result.churned_members,
            mrr_cents=result.total_mrr_cents,
        )
        return result

    async def generate_patron_credits(self, video_id: uuid.UUID) -> str:
        """Generate the patron credits block for video descriptions.

        Groups patrons by tier (highest first) and only includes those
        who opted in to public credits.
        """
        async with self._pool.connection() as conn:
            rows = await (await conn.execute(queries.LIST_PATRON_CREDITS)).fetchall()

        if not rows:
            return ""

        # Group by tier
        tiers: dict[str, list[str]] = {}
        for row in rows:
            r = cast("dict[str, Any]", row)
            tier = r["tier_name"] or "Supporter"
            tiers.setdefault(tier, []).append(r["name"])

        lines = ["\U0001f3c6 Special thanks to our Patrons:"]
        for tier_name, names in tiers.items():
            names_str = ", ".join(names)
            lines.append(f"[{tier_name}] {names_str}")
        lines.append("Support us on Patreon: https://patreon.com/crimemill")

        credits = "\n".join(lines)
        await logger.ainfo(
            "patron_credits_generated",
            video_id=str(video_id),
            patron_count=sum(len(n) for n in tiers.values()),
        )
        return credits

    async def post_patreon_early_access(
        self,
        video_id: uuid.UUID,
        youtube_video_id: str,
        title: str,
        early_access_hours: int = 48,
    ) -> bool:
        """Create a Patreon post with an early access (unlisted) link.

        Workflow:
        1. Video is already uploaded as UNLISTED on YouTube
        2. Share unlisted link on Patreon (patron-only post)
        3. After early_access_hours, the publish scheduler makes it public

        This is the #1 Patreon perk that drives conversions in true crime.
        """
        access_token = self._settings.patreon.access_token
        campaign_id = self._settings.patreon.campaign_id
        if not access_token or not campaign_id:
            await logger.awarning("patreon_early_access_skipped", reason="not configured")
            return False

        youtube_url = f"https://youtube.com/watch?v={youtube_video_id}"
        publish_time = datetime.now(UTC) + timedelta(hours=early_access_hours)

        post_payload = {
            "data": {
                "type": "post",
                "attributes": {
                    "title": f"\U0001f510 Early Access: {title}",
                    "content": (
                        f"Hey Patrons! Here's your exclusive early access link:\n\n"
                        f"\U0001f3ac {youtube_url}\n\n"
                        f"This video goes public in {early_access_hours} hours "
                        f"({publish_time.strftime('%B %d at %I:%M %p UTC')}).\n\n"
                        f"Thank you for supporting CrimeMill!"
                    ),
                    "is_paid": True,
                    "is_public": False,
                },
                "relationships": {
                    "campaign": {
                        "data": {"type": "campaign", "id": campaign_id},
                    },
                },
            },
        }

        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/vnd.api+json",
        }

        try:
            resp = await self._http.post(
                f"{PATREON_API_BASE}/posts",
                json=post_payload,
                headers=headers,
            )
            resp.raise_for_status()
            await logger.ainfo(
                "patreon_early_access_posted",
                video_id=str(video_id),
                youtube_url=youtube_url,
                goes_public_at=publish_time.isoformat(),
            )
            return True
        except Exception as exc:
            await logger.awarning("patreon_early_access_failed", error=str(exc))
            return False

    # ------------------------------------------------------------------
    # Topic submissions
    # ------------------------------------------------------------------

    async def process_topic_submissions(self) -> list[TopicSubmission]:
        """Ingest topic suggestions from Google Forms and Discord.

        Sources:
        1. Google Forms via Sheets API — fields: case name, why interesting,
           sources, submitter name
        2. Discord #suggest-a-case channel — bot monitors for new messages

        For each submission: deduplicate, score via topic_selector, store.
        """
        submissions: list[TopicSubmission] = []

        # 1. Google Forms (via Sheets API)
        sheet_id = self._settings.google_forms.sheet_id
        if sheet_id:
            forms_subs = await self._ingest_google_forms(sheet_id)
            submissions.extend(forms_subs)

        # 2. Discord #suggest-a-case
        if self._settings.discord.bot_token:
            discord_subs = await self._ingest_discord_suggestions()
            submissions.extend(discord_subs)

        await logger.ainfo(
            "topic_submissions_processed",
            total=len(submissions),
            google_forms=len([s for s in submissions if s.source == "google_forms"]),
            discord=len([s for s in submissions if s.source == "discord"]),
        )
        return submissions

    async def _ingest_google_forms(self, sheet_id: str) -> list[TopicSubmission]:
        """Fetch responses from a Google Sheet linked to a Google Form.

        Expected columns: Timestamp, Case Name, Why Interesting, Sources, Name
        """
        url = f"{GOOGLE_SHEETS_API}/{sheet_id}/values/A:E"
        submissions: list[TopicSubmission] = []

        try:
            resp = await self._http.get(
                url,
                params={"key": self._settings.google_forms.sheet_id},
            )
            resp.raise_for_status()
            data = resp.json()
            rows = data.get("values", [])[1:]  # skip header

            for row in rows:
                if len(row) < 2:
                    continue
                case_name = row[1] if len(row) > 1 else ""
                if not case_name:
                    continue

                sub_input = TopicSubmissionCreate(
                    source="google_forms",
                    case_name=case_name,
                    why_interesting=row[2] if len(row) > 2 else "",
                    source_links=[row[3]] if len(row) > 3 and row[3] else [],
                    submitter_name=row[4] if len(row) > 4 else "",
                )
                result = await self._store_submission(sub_input)
                if result:
                    submissions.append(result)
        except Exception as exc:
            await logger.awarning("google_forms_ingest_failed", error=str(exc))

        return submissions

    async def _ingest_discord_suggestions(self) -> list[TopicSubmission]:
        """Read recent messages from the #suggest-a-case channel."""
        channel_id = self._settings.discord.case_discussion_channel_id
        bot_token = self._settings.discord.bot_token
        if not channel_id or not bot_token:
            return []

        submissions: list[TopicSubmission] = []
        headers = {"Authorization": f"Bot {bot_token}"}

        try:
            resp = await self._http.get(
                f"{DISCORD_API_BASE}/channels/{channel_id}/messages",
                params={"limit": 50},
                headers=headers,
            )
            resp.raise_for_status()
            messages = resp.json()

            for msg in messages:
                content = msg.get("content", "").strip()
                if not content or msg.get("author", {}).get("bot"):
                    continue

                # Extract case name from the first line
                lines = content.split("\n")
                case_name = lines[0][:500]
                description = "\n".join(lines[1:])[:5000] if len(lines) > 1 else ""
                author_name = msg.get("author", {}).get("username", "")

                sub_input = TopicSubmissionCreate(
                    source="discord",
                    case_name=case_name,
                    description=description,
                    submitter_name=author_name,
                    submitter_contact=f"discord:{author_name}",
                )
                result = await self._store_submission(sub_input)
                if result:
                    submissions.append(result)
        except Exception as exc:
            await logger.awarning("discord_suggestions_ingest_failed", error=str(exc))

        return submissions

    async def _store_submission(
        self,
        sub: TopicSubmissionCreate,
    ) -> TopicSubmission | None:
        """Deduplicate and store a topic submission."""
        async with self._pool.connection() as conn:
            # Check for duplicates
            dupes = await (
                await conn.execute(
                    queries.DEDUPLICATE_SUBMISSION,
                    {"case_name": sub.case_name},
                )
            ).fetchall()
            if dupes:
                await logger.ainfo(
                    "submission_deduplicated",
                    case_name=sub.case_name,
                    existing_ids=[str(cast("dict[str, Any]", d)["id"]) for d in dupes],
                )
                return None

            # Score via topic selector (best-effort)
            score: Decimal | None = None
            try:
                from src.models.topic import TopicCandidate
                from src.services.topic_selector import TopicSelector

                candidate = TopicCandidate(
                    title=sub.case_name,
                    description=sub.description,
                )
                scored = TopicSelector.score_topic(candidate)
                score = Decimal(str(scored.composite_score))
            except Exception:
                pass  # scoring is optional

            row = await (
                await conn.execute(
                    queries.INSERT_TOPIC_SUBMISSION,
                    {
                        "source": sub.source,
                        "submitter_name": sub.submitter_name,
                        "submitter_contact": sub.submitter_contact,
                        "case_name": sub.case_name,
                        "description": sub.description,
                        "why_interesting": sub.why_interesting,
                        "source_links": sub.source_links,
                        "score": score,
                    },
                )
            ).fetchone()

            if row:
                return TopicSubmission.from_row(cast("dict[str, Any]", row))
        return None

    async def create_manual_submission(
        self,
        sub: TopicSubmissionCreate,
    ) -> TopicSubmission | None:
        """Create a submission from the CLI or API (manual source)."""
        return await self._store_submission(sub)

    async def review_submission(
        self,
        submission_id: uuid.UUID,
        status: str,
        assigned_topic_id: uuid.UUID | None = None,
        assigned_video_id: uuid.UUID | None = None,
    ) -> TopicSubmission | None:
        """Accept or reject a topic submission."""
        async with self._pool.connection() as conn:
            row = await (
                await conn.execute(
                    queries.UPDATE_TOPIC_SUBMISSION_STATUS,
                    {
                        "id": submission_id,
                        "status": status,
                        "assigned_topic_id": assigned_topic_id,
                        "assigned_video_id": assigned_video_id,
                    },
                )
            ).fetchone()
        if row:
            return TopicSubmission.from_row(cast("dict[str, Any]", row))
        return None

    # ------------------------------------------------------------------
    # Community metrics
    # ------------------------------------------------------------------

    async def get_community_metrics(self, channel_id: uuid.UUID) -> CommunityMetrics:
        """Aggregate community health metrics for a channel.

        Combines Discord member counts, Patreon stats, topic submission
        activity, and patron retention.
        """
        discord_total = 0
        discord_active = 0

        # Discord metrics (via bot API)
        guild_id = self._settings.discord.guild_id
        bot_token = self._settings.discord.bot_token
        if guild_id and bot_token:
            try:
                resp = await self._http.get(
                    f"{DISCORD_API_BASE}/guilds/{guild_id}",
                    params={"with_counts": "true"},
                    headers={"Authorization": f"Bot {bot_token}"},
                )
                resp.raise_for_status()
                guild_data = resp.json()
                discord_total = guild_data.get("approximate_member_count", 0)
                discord_active = guild_data.get("approximate_presence_count", 0)
            except Exception as exc:
                await logger.awarning("discord_metrics_failed", error=str(exc))

        async with self._pool.connection() as conn:
            # Patreon stats
            patron_row_raw = await (await conn.execute(queries.COUNT_ACTIVE_PATRONS)).fetchone()
            patron_row = cast("dict[str, Any]", patron_row_raw) if patron_row_raw else None
            patron_count = patron_row["patron_count"] if patron_row else 0
            mrr_cents = patron_row["total_mrr_cents"] if patron_row else 0

            # Topic submissions this month
            sub_row_raw = await (
                await conn.execute(queries.COUNT_SUBMISSIONS_THIS_MONTH)
            ).fetchone()
            sub_row = cast("dict[str, Any]", sub_row_raw) if sub_row_raw else None
            submissions_count = sub_row["total"] if sub_row else 0

            # Community-sourced videos
            cs_row_raw = await (
                await conn.execute(queries.COUNT_COMMUNITY_SOURCED_VIDEOS)
            ).fetchone()
            cs_row = cast("dict[str, Any]", cs_row_raw) if cs_row_raw else None
            cs_count = cs_row["total"] if cs_row else 0

            # Patron retention rate
            ret_row_raw = await (await conn.execute(queries.PATRON_RETENTION_RATE)).fetchone()
            ret_row = cast("dict[str, Any]", ret_row_raw) if ret_row_raw else None
            retention = float(ret_row["retention_rate"]) if ret_row else 0.0

        return CommunityMetrics(
            channel_id=channel_id,
            discord_members_total=discord_total,
            discord_active_7d=discord_active,
            patreon_patron_count=patron_count,
            patreon_mrr_usd=Decimal(str(mrr_cents)) / Decimal("100"),
            submissions_this_month=submissions_count,
            community_sourced_videos=cs_count,
            patron_retention_rate=retention,
        )
