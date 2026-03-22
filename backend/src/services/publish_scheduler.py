"""Content scheduling system — multi-channel network grid and human review queue.

Manages the publishing calendar across channels, enforces timing rules
(optimal windows, notification caps, seasonal cadence), and provides
the review queue for human approval before publish.
"""

from __future__ import annotations

import json
import uuid
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING, Any, cast
from zoneinfo import ZoneInfo

import structlog

from src.models.schedule import (
    CalendarEntry,
    NetworkGrid,
    PublishingCalendar,
    ScheduleSlot,
    VideoForReview,
    WeeklySlot,
)

if TYPE_CHECKING:
    from psycopg import AsyncConnection
    from psycopg_pool import AsyncConnectionPool

    from src.config import Settings
    from src.services.youtube_uploader import YouTubeUploader

logger = structlog.get_logger()

# ---------------------------------------------------------------------------
# Scheduling constants (from bible §7B.1)
# ---------------------------------------------------------------------------

# Optimal publish window
_PEAK_DAYS = {"Wednesday", "Thursday", "Friday", "Saturday"}
_PEAK_HOUR_MIN = 14  # 2 PM CT (upload ~1h before peak)
_PEAK_HOUR_MAX = 17  # 5 PM CT

# Cadence
_DEFAULT_MAX_PER_WEEK = 5
_Q4_MAX_PER_WEEK = 7
_Q1_MAX_PER_WEEK = 4

# YouTube notification cap: 3 per subscriber per 24h
_MAX_NOTIFICATIONS_PER_DAY = 3

# Sunday is rest day
_SCHEDULE_DAYS: list[str] = [
    "Monday",
    "Tuesday",
    "Wednesday",
    "Thursday",
    "Friday",
    "Saturday",
]

# Default slot hours for distributing channels across the week
_DEFAULT_SLOT_HOURS = [14, 15, 16]

# Seasonal quarters
_Q4_MONTHS = {10, 11, 12}
_Q1_MONTHS = {1, 2, 3}


# ---------------------------------------------------------------------------
# SQL queries (scheduler-specific)
# ---------------------------------------------------------------------------

_GET_CHANNELS = """
SELECT id, name, handle, status FROM channels WHERE status = 'active';
"""

_GET_CHANNEL_CONFIG = """
SELECT channel_id, grid_slots, max_videos_per_week, auto_publish,
       timezone, q4_boost_enabled
FROM channel_schedule_config
WHERE channel_id = %(channel_id)s;
"""

_GET_ALL_CONFIGS = """
SELECT channel_id, grid_slots, max_videos_per_week, auto_publish,
       timezone, q4_boost_enabled
FROM channel_schedule_config;
"""

_GET_SCHEDULED_VIDEOS = """
SELECT ps.id, ps.video_id, ps.channel_id, ps.scheduled_publish_at, ps.status
FROM publish_schedule ps
WHERE ps.scheduled_publish_at >= %(start)s
  AND ps.scheduled_publish_at < %(end)s
  AND ps.status IN ('scheduled', 'publishing')
ORDER BY ps.scheduled_publish_at;
"""

_GET_CHANNEL_SCHEDULED = """
SELECT ps.scheduled_publish_at
FROM publish_schedule ps
WHERE ps.channel_id = %(channel_id)s
  AND ps.scheduled_publish_at >= %(after)s
  AND ps.status IN ('scheduled', 'publishing')
ORDER BY ps.scheduled_publish_at;
"""

_INSERT_SCHEDULE = """
INSERT INTO publish_schedule (video_id, channel_id, scheduled_publish_at, status)
VALUES (%(video_id)s, %(channel_id)s, %(publish_at)s, 'scheduled')
ON CONFLICT (video_id) DO UPDATE SET
    scheduled_publish_at = EXCLUDED.scheduled_publish_at,
    status = 'scheduled'
RETURNING *;
"""

_UPDATE_SCHEDULE_STATUS = """
UPDATE publish_schedule
SET status = %(status)s, actual_published_at = %(published_at)s
WHERE video_id = %(video_id)s
RETURNING *;
"""

_UPDATE_SCHEDULE_TIME = """
UPDATE publish_schedule
SET scheduled_publish_at = %(publish_at)s
WHERE video_id = %(video_id)s
RETURNING *;
"""

_APPROVE_SCHEDULE = """
UPDATE publish_schedule
SET approved_at = now(), reviewer_notes = %(notes)s, status = 'scheduled'
WHERE video_id = %(video_id)s
RETURNING *;
"""

_CANCEL_SCHEDULE = """
UPDATE publish_schedule
SET status = 'cancelled'
WHERE video_id = %(video_id)s
RETURNING *;
"""

_GET_REVIEW_QUEUE = """
SELECT
    v.id AS video_id,
    v.title,
    v.channel_id,
    c.name AS channel_name,
    v.created_at,
    v.updated_at AS assembled_at,
    COALESCE(SUM(gc.cost_usd), 0) AS total_cost_usd
FROM videos v
JOIN channels c ON c.id = v.channel_id
LEFT JOIN generation_costs gc ON gc.video_id = v.id
WHERE v.status = 'assembled'
GROUP BY v.id, v.title, v.channel_id, c.name, v.created_at, v.updated_at
ORDER BY v.updated_at ASC;
"""

_GET_SCHEDULE_BY_VIDEO = """
SELECT * FROM publish_schedule WHERE video_id = %(video_id)s;
"""

_UPSERT_CHANNEL_CONFIG = """
INSERT INTO channel_schedule_config (channel_id, grid_slots, max_videos_per_week)
VALUES (%(channel_id)s, %(grid_slots)s, %(max_videos_per_week)s)
ON CONFLICT (channel_id) DO UPDATE SET
    grid_slots = EXCLUDED.grid_slots,
    max_videos_per_week = EXCLUDED.max_videos_per_week,
    updated_at = now()
RETURNING *;
"""

_COUNT_CHANNEL_WEEK = """
SELECT COUNT(*) AS n
FROM publish_schedule
WHERE channel_id = %(channel_id)s
  AND scheduled_publish_at >= %(week_start)s
  AND scheduled_publish_at < %(week_end)s
  AND status IN ('scheduled', 'publishing', 'published');
"""


class PublishScheduler:
    """Manages the publishing calendar across multiple channels.

    Enforces network grid rules, optimal timing windows, seasonal cadence
    adjustments, and the human review queue.
    """

    def __init__(
        self,
        settings: Settings,
        db_pool: AsyncConnectionPool,
        youtube_uploader: YouTubeUploader,
    ) -> None:
        self._settings = settings
        self._pool = db_pool
        self._yt = youtube_uploader

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def schedule_video(
        self,
        video_id: uuid.UUID,
        preferred_date: date | None = None,
    ) -> ScheduleSlot:
        """Assign a publish slot to a video following network grid rules.

        Rules:
        1. Optimal window: Wed–Sat, 2–5 PM CT
        2. Never two overlapping-audience channels on the same day
        3. Upload ~1h before peak activity
        4. Respect per-channel cadence (max 1/day, target 5/week)
        5. Seasonal: Q4 boost to 7/week, Q1 reduce to 4/week
        """
        async with self._pool.connection() as conn:
            cur = await conn.execute(
                "SELECT id, channel_id, title FROM videos WHERE id = %(video_id)s",
                {"video_id": video_id},
            )
            video = cast("dict[str, Any] | None", await cur.fetchone())
            if video is None:
                raise ValueError(f"Video {video_id} not found")

            channel_id: uuid.UUID = video["channel_id"]

            grid = await self._load_network_grid(conn)

            now = _now_ct()
            after = now
            if preferred_date:
                preferred_dt = datetime.combine(
                    preferred_date,
                    time(14, 0),
                    tzinfo=_CT,
                )
                if preferred_dt > now:
                    after = preferred_dt - timedelta(hours=1)

            publish_at = await self._find_next_slot(conn, channel_id, grid, after)

            cur = await conn.execute(
                _INSERT_SCHEDULE,
                {
                    "video_id": video_id,
                    "channel_id": channel_id,
                    "publish_at": publish_at,
                },
            )
            await conn.commit()

        slot = _make_schedule_slot(video_id, channel_id, publish_at)

        await logger.ainfo(
            "video_scheduled",
            video_id=str(video_id),
            publish_at=publish_at.isoformat(),
            day=slot.day_of_week,
        )
        return slot

    async def get_publishing_calendar(
        self,
        days_ahead: int = 14,
    ) -> PublishingCalendar:
        """Return the full multi-channel publishing calendar."""
        now = _now_ct()
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        end = start + timedelta(days=days_ahead)

        async with self._pool.connection() as conn:
            # Channels
            cur = await conn.execute(_GET_CHANNELS)
            channels = {
                r["id"]: r["name"] for r in cast("list[dict[str, Any]]", await cur.fetchall())
            }

            # Scheduled videos
            cur = await conn.execute(
                _GET_SCHEDULED_VIDEOS,
                {"start": start, "end": end},
            )
            scheduled_rows = cast("list[dict[str, Any]]", await cur.fetchall())

            grid = await self._load_network_grid(conn)

        # Build occupied set
        occupied: dict[tuple[uuid.UUID, date], dict[str, Any]] = {}
        for row in scheduled_rows:
            dt: datetime = row["scheduled_publish_at"]
            key = (row["channel_id"], dt.date())
            occupied[key] = {
                "video_id": row["video_id"],
                "time": dt.time(),
                "status": row["status"],
            }

        entries: list[CalendarEntry] = []
        open_slots: list[datetime] = []
        conflicts: list[str] = []

        # Walk each day
        current = start
        while current < end:
            d = current.date()
            day_name = d.strftime("%A")
            if day_name == "Sunday":
                current += timedelta(days=1)
                continue

            for ch_id, ch_name in channels.items():
                ch_slots = grid.channel_slots.get(ch_id, [])
                for ws in ch_slots:
                    if ws.day != day_name:
                        continue

                    slot_dt = datetime.combine(
                        d,
                        time(ws.hour, ws.minute),
                        tzinfo=_CT,
                    )
                    key = (ch_id, d)

                    if key in occupied:
                        occ = occupied[key]
                        entries.append(
                            CalendarEntry(
                                date=d,
                                time=occ["time"],
                                channel_id=ch_id,
                                channel_name=ch_name,
                                video_id=occ["video_id"],
                                video_title=None,
                                status="scheduled" if occ["status"] == "scheduled" else "published",
                            )
                        )
                    else:
                        entries.append(
                            CalendarEntry(
                                date=d,
                                time=time(ws.hour, ws.minute),
                                channel_id=ch_id,
                                channel_name=ch_name,
                                status="open",
                            )
                        )
                        open_slots.append(slot_dt)

            # Check conflicts: two channels on the same day
            day_channels = [
                e.channel_name
                for e in entries
                if e.date == d and e.status in ("scheduled", "published")
            ]
            if len(day_channels) > 1:
                conflicts.append(f"{d.isoformat()}: {', '.join(day_channels)} overlap")

            current += timedelta(days=1)

        return PublishingCalendar(
            slots=entries,
            open_slots=open_slots,
            conflicts=conflicts,
        )

    async def get_review_queue(self) -> list[VideoForReview]:
        """Return all videos in 'assembled' status awaiting human review."""
        async with self._pool.connection() as conn:
            cur = await conn.execute(_GET_REVIEW_QUEUE)
            rows = cast("list[dict[str, Any]]", await cur.fetchall())

            grid = await self._load_network_grid(conn)

        result: list[VideoForReview] = []
        for row in rows:
            channel_id = row["channel_id"]
            assembled_at: datetime = row["assembled_at"]
            pipeline_minutes = (
                (assembled_at - row["created_at"]).total_seconds() / 60
                if assembled_at and row["created_at"]
                else 0.0
            )

            # Suggest a slot
            suggested: datetime | None = None
            try:
                async with self._pool.connection() as conn2:
                    suggested = await self._find_next_slot(
                        conn2,
                        channel_id,
                        grid,
                        _now_ct(),
                    )
            except Exception:
                pass

            result.append(
                VideoForReview(
                    video_id=row["video_id"],
                    title=row["title"] or "",
                    channel_name=row["channel_name"],
                    total_cost_usd=Decimal(str(row["total_cost_usd"])),
                    pipeline_duration_minutes=round(pipeline_minutes, 1),
                    self_cert_recommendation=_auto_classify(row["title"] or ""),
                    suggested_publish_slot=suggested,
                    assembled_at=assembled_at,
                )
            )

        return result

    async def approve_for_publish(
        self,
        video_id: uuid.UUID,
        reviewer_notes: str = "",
    ) -> ScheduleSlot:
        """Human approves a video — schedule it and trigger upload."""
        slot = await self.schedule_video(video_id)

        async with self._pool.connection() as conn:
            # Record approval
            await conn.execute(
                _APPROVE_SCHEDULE,
                {"video_id": video_id, "notes": reviewer_notes},
            )

            # Move video to 'uploading'
            await conn.execute(
                "UPDATE videos SET status = 'uploading', updated_at = now() "
                "WHERE id = %(video_id)s",
                {"video_id": video_id},
            )

            # Enqueue youtube_upload stage
            from src.pipeline.orchestrator import Orchestrator

            orch = Orchestrator(cast("AsyncConnection[dict[str, object]]", conn))
            await orch._create_job(
                video_id,
                "youtube_upload",
                {"scheduled_publish_at": slot.publish_at.isoformat()},
                priority=5,
            )
            await conn.commit()

        await logger.ainfo(
            "video_approved",
            video_id=str(video_id),
            publish_at=slot.publish_at.isoformat(),
        )
        return slot

    async def reject_video(
        self,
        video_id: uuid.UUID,
        reason: str,
    ) -> None:
        """Reject a video — cancel it and free the slot."""
        async with self._pool.connection() as conn:
            await conn.execute(
                _CANCEL_SCHEDULE,
                {"video_id": video_id},
            )
            await conn.execute(
                "UPDATE videos SET status = 'cancelled', "
                "error_message = %(reason)s, updated_at = now() "
                "WHERE id = %(video_id)s",
                {"video_id": video_id, "reason": reason},
            )
            await conn.commit()

        await logger.ainfo(
            "video_rejected",
            video_id=str(video_id),
            reason=reason,
        )

    async def reschedule(
        self,
        video_id: uuid.UUID,
        new_datetime: datetime,
    ) -> ScheduleSlot:
        """Move a scheduled video to a different slot."""
        async with self._pool.connection() as conn:
            cur = await conn.execute(
                "SELECT channel_id FROM publish_schedule WHERE video_id = %(video_id)s",
                {"video_id": video_id},
            )
            row = cast("dict[str, Any] | None", await cur.fetchone())
            if row is None:
                raise ValueError(f"No schedule found for video {video_id}")

            channel_id: uuid.UUID = row["channel_id"]

            # Validate: not same day as another channel's video
            _grid = await self._load_network_grid(conn)  # noqa: F841 — grid pre-loaded for future slot optimisation
            conflict = await self._check_day_conflict(
                conn,
                channel_id,
                new_datetime.date(),
                video_id,
            )
            if conflict:
                raise ValueError(
                    f"Slot conflict: another channel already scheduled on "
                    f"{new_datetime.date().isoformat()}"
                )

            await conn.execute(
                _UPDATE_SCHEDULE_TIME,
                {"video_id": video_id, "publish_at": new_datetime},
            )

            # If already uploaded to YouTube, update scheduled time
            cur = await conn.execute(
                "SELECT youtube_video_id FROM videos WHERE id = %(video_id)s",
                {"video_id": video_id},
            )
            vid_row = cast("dict[str, Any] | None", await cur.fetchone())
            if vid_row and vid_row.get("youtube_video_id"):
                try:
                    await self._yt._update_video_status(
                        vid_row["youtube_video_id"],
                        channel_id,
                        privacy_status="private",
                        publish_at=new_datetime.isoformat(),
                    )
                except Exception:
                    await logger.awarning(
                        "youtube_reschedule_failed",
                        video_id=str(video_id),
                    )

            await conn.commit()

        slot = _make_schedule_slot(video_id, channel_id, new_datetime)
        await logger.ainfo(
            "video_rescheduled",
            video_id=str(video_id),
            new_publish_at=new_datetime.isoformat(),
        )
        return slot

    async def get_next_slot(self, channel_id: uuid.UUID) -> ScheduleSlot:
        """Return the next available slot for a channel (no video assigned)."""
        async with self._pool.connection() as conn:
            grid = await self._load_network_grid(conn)
            publish_at = await self._find_next_slot(
                conn,
                channel_id,
                grid,
                _now_ct(),
            )

        return _make_schedule_slot(
            uuid.UUID(int=0),
            channel_id,
            publish_at,
        )

    # ------------------------------------------------------------------
    # Network grid
    # ------------------------------------------------------------------

    def _build_network_grid(
        self,
        channels: list[dict[str, Any]],
    ) -> NetworkGrid:
        """Build default grid: distribute channels across Mon–Sat, 2 slots each."""
        slots: dict[uuid.UUID, list[WeeklySlot]] = {}
        day_idx = 0

        for ch in channels:
            ch_id = ch["id"]
            ch_slots: list[WeeklySlot] = []

            # Assign 2 non-adjacent days per channel
            for _ in range(2):
                day = _SCHEDULE_DAYS[day_idx % len(_SCHEDULE_DAYS)]
                hour = _DEFAULT_SLOT_HOURS[day_idx % len(_DEFAULT_SLOT_HOURS)]
                ch_slots.append(WeeklySlot(day=day, hour=hour))  # type: ignore[arg-type]
                day_idx += 1

            slots[ch_id] = ch_slots

        return NetworkGrid(channel_slots=slots)

    async def _load_network_grid(self, conn: Any) -> NetworkGrid:
        """Load the grid from channel_schedule_config, or build defaults."""
        cur = await conn.execute(_GET_ALL_CONFIGS)
        configs = cast("list[dict[str, Any]]", await cur.fetchall())

        cur2 = await conn.execute(_GET_CHANNELS)
        channels = cast("list[dict[str, Any]]", await cur2.fetchall())

        if not configs:
            # No config yet — build default grid and persist
            grid = self._build_network_grid(channels)
            for ch_id, ch_slots in grid.channel_slots.items():
                await conn.execute(
                    _UPSERT_CHANNEL_CONFIG,
                    {
                        "channel_id": ch_id,
                        "grid_slots": json.dumps([s.model_dump() for s in ch_slots]),
                        "max_videos_per_week": _DEFAULT_MAX_PER_WEEK,
                    },
                )
            await conn.commit()
            return grid

        # Parse configs into grid
        slot_map: dict[uuid.UUID, list[WeeklySlot]] = {}
        for cfg in configs:
            raw = cfg["grid_slots"]
            if isinstance(raw, str):
                raw = json.loads(raw)
            slot_map[cfg["channel_id"]] = [WeeklySlot.model_validate(s) for s in raw]

        return NetworkGrid(channel_slots=slot_map)

    async def _find_next_slot(
        self,
        conn: Any,
        channel_id: uuid.UUID,
        grid: NetworkGrid,
        after: datetime,
    ) -> datetime:
        """Find next available publish slot for a channel in the grid."""
        ch_slots = grid.channel_slots.get(channel_id, [])
        if not ch_slots:
            # Fallback: next Wednesday at 3 PM CT
            return _next_weekday(after, "Wednesday", 15)

        # Get already-scheduled dates for this channel
        cur = await conn.execute(
            _GET_CHANNEL_SCHEDULED,
            {"channel_id": channel_id, "after": after},
        )
        occupied_dts = {
            r["scheduled_publish_at"] for r in cast("list[dict[str, Any]]", await cur.fetchall())
        }

        # Walk forward day by day for up to 60 days
        candidate = after
        for _ in range(60 * len(ch_slots)):
            d = candidate.date()
            day_name = d.strftime("%A")

            for ws in ch_slots:
                if ws.day != day_name:
                    continue

                slot_dt = datetime.combine(
                    d,
                    time(ws.hour, ws.minute),
                    tzinfo=_CT,
                )
                if slot_dt <= after:
                    continue
                if slot_dt in occupied_dts:
                    continue

                # Check same-day conflict with other channels
                conflict = await self._check_day_conflict(
                    conn,
                    channel_id,
                    d,
                )
                if conflict:
                    continue

                # Check weekly cadence cap
                over_cap = await self._is_over_weekly_cap(
                    conn,
                    channel_id,
                    d,
                )
                if over_cap:
                    continue

                return slot_dt

            candidate += timedelta(days=1)

        # Absolute fallback
        return after + timedelta(days=1)

    async def _check_day_conflict(
        self,
        conn: Any,
        channel_id: uuid.UUID,
        day: date,
        exclude_video: uuid.UUID | None = None,
    ) -> bool:
        """Return True if another channel has a video scheduled on this day."""
        day_start = datetime.combine(day, time(0, 0), tzinfo=_CT)
        day_end = day_start + timedelta(days=1)

        cur = await conn.execute(
            _GET_SCHEDULED_VIDEOS,
            {"start": day_start, "end": day_end},
        )
        rows = cast("list[dict[str, Any]]", await cur.fetchall())

        for row in rows:
            if row["channel_id"] != channel_id:
                if exclude_video and row["video_id"] == exclude_video:
                    continue
                return True
        return False

    async def _is_over_weekly_cap(
        self,
        conn: Any,
        channel_id: uuid.UUID,
        day: date,
    ) -> bool:
        """Check if this channel already hit its weekly cadence limit."""
        # Monday-based week
        monday = day - timedelta(days=day.weekday())
        week_start = datetime.combine(monday, time(0, 0), tzinfo=_CT)
        week_end = week_start + timedelta(days=7)

        cur = await conn.execute(
            _COUNT_CHANNEL_WEEK,
            {
                "channel_id": channel_id,
                "week_start": week_start,
                "week_end": week_end,
            },
        )
        row = cast("dict[str, Any] | None", await cur.fetchone())
        count = row["n"] if row else 0

        # Determine cap based on season
        cap = _weekly_cap_for_date(day)

        return count >= cap

    async def _auto_schedule_batch(self) -> int:
        """Auto-schedule all approved assembled videos. Returns count."""
        async with self._pool.connection() as conn:
            cur = await conn.execute(
                "SELECT v.id FROM videos v "
                "JOIN channel_schedule_config csc ON csc.channel_id = v.channel_id "
                "WHERE v.status = 'assembled' AND csc.auto_publish = true "
                "AND NOT EXISTS ("
                "  SELECT 1 FROM publish_schedule ps "
                "  WHERE ps.video_id = v.id AND ps.status != 'cancelled'"
                ") "
                "ORDER BY v.created_at ASC",
            )
            rows = cast("list[dict[str, Any]]", await cur.fetchall())

        count = 0
        for row in rows:
            try:
                await self.approve_for_publish(row["id"])
                count += 1
            except Exception:
                await logger.awarning(
                    "auto_schedule_failed",
                    video_id=str(row["id"]),
                )
        return count


# ---------------------------------------------------------------------------
# Module-level helpers
# ---------------------------------------------------------------------------

_CT = ZoneInfo("America/Chicago")


def _now_ct() -> datetime:
    return datetime.now(tz=_CT)


def _is_peak(dt: datetime) -> bool:
    """Check if datetime falls in peak window (Wed–Sat, 2–5 PM CT)."""
    ct = dt.astimezone(_CT)
    return ct.strftime("%A") in _PEAK_DAYS and _PEAK_HOUR_MIN <= ct.hour <= _PEAK_HOUR_MAX


def _is_q4(dt: datetime) -> bool:
    return dt.month in _Q4_MONTHS


def _weekly_cap_for_date(d: date) -> int:
    if d.month in _Q4_MONTHS:
        return _Q4_MAX_PER_WEEK
    if d.month in _Q1_MONTHS:
        return _Q1_MAX_PER_WEEK
    return _DEFAULT_MAX_PER_WEEK


def _next_weekday(after: datetime, day_name: str, hour: int) -> datetime:
    """Return the next occurrence of *day_name* at *hour*:00 CT after *after*."""
    target_idx = _SCHEDULE_DAYS.index(day_name)
    current_idx = after.weekday()
    days_ahead = (target_idx - current_idx) % 7
    if days_ahead == 0:
        days_ahead = 7
    d = after.date() + timedelta(days=days_ahead)
    return datetime.combine(d, time(hour, 0), tzinfo=_CT)


def _make_schedule_slot(
    video_id: uuid.UUID,
    channel_id: uuid.UUID,
    publish_at: datetime,
) -> ScheduleSlot:
    ct = publish_at.astimezone(_CT)
    return ScheduleSlot(
        video_id=video_id,
        channel_id=channel_id,
        publish_at=publish_at,
        day_of_week=ct.strftime("%A"),
        is_peak_slot=_is_peak(publish_at),
        is_q4=_is_q4(publish_at),
    )


def _auto_classify(title: str) -> dict[str, object]:
    """Basic auto-classification for self-certification recommendation."""
    title_lower = title.lower()
    flags: dict[str, object] = {
        "violence_mentioned": any(
            w in title_lower for w in ("murder", "kill", "death", "shot", "stab")
        ),
        "drugs_mentioned": any(
            w in title_lower for w in ("drug", "cartel", "trafficking", "cocaine")
        ),
        "fraud_only": any(w in title_lower for w in ("fraud", "scam", "ponzi", "embezzle")),
        "recommendation": "standard",
    }
    if flags["violence_mentioned"] or flags["drugs_mentioned"]:
        flags["recommendation"] = "limited_ads"
    return flags
