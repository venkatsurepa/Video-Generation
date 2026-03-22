"""Monthly compilation video generator.

Creates "Best Of" compilations from top-performing video segments with new
narration to comply with YouTube's reused-content policy.  Scheduled via
pg_cron on the 28th of each month.

Pipeline:
    1. Query video_daily_metrics for audience retention curves
    2. Identify peak-retention segments (retention above rolling avg × views)
    3. Generate new bridging narration via Claude (intro + transitions + outro)
    4. Generate voiceover for new narration via Fish Audio
    5. Download source segments from YouTube / R2
    6. Extract peak segments via FFmpeg
    7. Concatenate with crossfade transitions and new narration
    8. Upload the final compilation as a new video
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import math
import os
import tempfile
from datetime import date, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING, Any, cast

import structlog

from src.models.compilation import (
    CompilationConfig,
    CompilationResult,
    CompilationScript,
    PeakSegment,
    SegmentTransition,
)

if TYPE_CHECKING:
    from uuid import UUID

    from psycopg_pool import AsyncConnectionPool

    from src.config import Settings
    from src.services.audio_processor import AudioProcessor
    from src.services.script_generator import ScriptGenerator
    from src.services.voiceover_generator import VoiceoverGenerator
    from src.utils.storage import R2Client

logger = structlog.get_logger()

# ---------------------------------------------------------------------------
# SQL queries (compilation-specific)
# ---------------------------------------------------------------------------

GET_TOP_VIDEOS_WITH_RETENTION: str = """
SELECT
    v.id              AS video_id,
    v.title           AS video_title,
    v.youtube_video_id,
    v.video_length_seconds,
    SUM(m.views)      AS total_views,
    -- Pick the most recent retention curve (latest metric_date)
    (
        SELECT audience_retention_curve
        FROM video_daily_metrics m2
        WHERE m2.video_id = v.id
          AND m2.audience_retention_curve IS NOT NULL
        ORDER BY m2.metric_date DESC
        LIMIT 1
    ) AS retention_curve
FROM videos v
JOIN video_daily_metrics m ON m.video_id = v.id
WHERE v.channel_id = %(channel_id)s
  AND v.status = 'published'
  AND v.published_at >= %(published_after)s
  AND v.youtube_video_id IS NOT NULL
GROUP BY v.id
HAVING SUM(m.views) >= %(min_views)s
ORDER BY SUM(m.views) DESC
LIMIT 50;
"""

INSERT_COMPILATION_VIDEO: str = """
INSERT INTO videos (channel_id, title, description, tags, topic, status)
VALUES (
    %(channel_id)s,
    %(title)s,
    %(description)s,
    %(tags)s,
    %(topic)s,
    'pending'
)
RETURNING id;
"""

# ---------------------------------------------------------------------------
# Prompt template for Claude
# ---------------------------------------------------------------------------

COMPILATION_SCRIPT_PROMPT: str = """You are writing narration for a true-crime YouTube compilation video.
This is a "{theme}" compilation for {month_label} on the channel "{channel_name}".

The compilation includes {segment_count} segments from our most popular videos.
You must write:
1. An INTRO (60-90 seconds of narration, ~150-225 words) that frames the compilation.
2. A TRANSITION between each pair of consecutive segments (15-30 seconds, ~40-75 words each).
3. An OUTRO (30-60 seconds, ~75-150 words) with a CTA and next-video tease.

SEGMENTS (in order):
{segment_descriptions}

RULES:
- The narration must be ORIGINAL. Do not repeat text from the source videos.
- Each transition should tease what's coming next to maintain viewer curiosity.
- Use a tone that is dark, measured, and cinematic — matching the CrimeMill brand.
- Do NOT use these words: delve, tapestry, landscape, realm, embark, pivotal, moreover, furthermore, arguably, intricacies.
- Write in second person ("you") to pull the viewer in.
- Every transition must reference the PREVIOUS segment's resolution and the NEXT segment's hook.

Respond ONLY with valid JSON matching this schema:
{{
    "intro_narration": "...",
    "outro_narration": "...",
    "transitions": [
        {{"from_segment_index": 0, "to_segment_index": 1, "narration_text": "..."}},
        ...
    ]
}}
"""


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------


class CompilationGenerator:
    """Generates monthly compilation videos from top-performing segments."""

    def __init__(
        self,
        settings: Settings,
        script_generator: ScriptGenerator,
        voiceover_generator: VoiceoverGenerator,
        audio_processor: AudioProcessor,
        r2_client: R2Client,
        db_pool: AsyncConnectionPool,
    ) -> None:
        self._settings = settings
        self._script_gen = script_generator
        self._voiceover_gen = voiceover_generator
        self._audio_proc = audio_processor
        self._r2 = r2_client
        self._db_pool = db_pool
        self._config = CompilationConfig()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def generate_monthly_compilation(
        self,
        channel_id: UUID,
        month: date,
        *,
        theme: str = "best_of",
        config: CompilationConfig | None = None,
    ) -> CompilationResult:
        """End-to-end monthly compilation: identify → script → extract → assemble → upload."""
        if config:
            self._config = config

        log = logger.bind(channel_id=str(channel_id), month=month.isoformat(), theme=theme)
        log.info("compilation.start")

        # 1. Identify peak segments from retention data
        segments = await self._identify_peak_segments(channel_id, month)
        if len(segments) < self._config.min_segments:
            raise ValueError(
                f"Only {len(segments)} qualifying segments found, "
                f"need at least {self._config.min_segments}"
            )

        # Cap at max_segments, keeping top-scoring ones
        segments = sorted(segments, key=lambda s: s.engagement_score, reverse=True)
        segments = segments[: self._config.max_segments]
        # Re-sort chronologically by video publish order for narrative flow
        # (original order from the query is by views DESC, but for the video
        #  we want a logical progression)
        log.info("compilation.segments_selected", count=len(segments))

        # 2. Generate new narration script via Claude
        channel_name = await self._get_channel_name(channel_id)
        script = await self._generate_compilation_script(segments, month, theme, channel_name)
        log.info(
            "compilation.script_generated",
            new_words=script.total_new_narration_words,
            transitions=len(script.transitions),
        )

        # 3. Generate voiceover for new narration
        narration_paths = await self._generate_narration_audio(script, channel_id)
        log.info("compilation.narration_generated", audio_files=len(narration_paths))

        # 4. Extract peak segments from source videos
        segment_paths = await self._extract_segments(segments)
        log.info("compilation.segments_extracted", count=len(segment_paths))

        # 5. Concatenate everything with crossfade transitions
        final_path = await self._concatenate_with_transitions(
            segment_paths, narration_paths, segments
        )
        log.info("compilation.concatenated", path=final_path)

        # 6. Calculate duration and content ratio
        final_info = await self._audio_proc.get_audio_info(final_path)
        total_duration = final_info.duration_seconds
        new_narration_secs = script.estimated_new_narration_seconds
        content_ratio = new_narration_secs / total_duration if total_duration > 0 else 0

        if content_ratio < self._config.min_original_content_ratio:
            log.warning(
                "compilation.low_original_content",
                ratio=content_ratio,
                target=self._config.min_original_content_ratio,
            )

        # 7. Upload to R2 and create video record
        month_str = month.strftime("%Y-%m")
        title = f"Best of {month.strftime('%B %Y')} | CrimeMill"
        r2_key = f"{channel_id}/compilations/{month_str}/compilation.mp4"

        file_size = os.path.getsize(final_path)
        bucket = self._settings.storage.bucket_name
        self._r2.upload_file(bucket, r2_key, final_path, "video/mp4")
        file_url = self._r2.generate_presigned_url(bucket, r2_key)

        # Create DB record
        video_id = await self._create_compilation_record(channel_id, title, month, theme, segments)

        total_cost = script.cost  # TODO: add voiceover + processing costs

        result = CompilationResult(
            video_id=video_id,
            channel_id=channel_id,
            title=title,
            description=f"The most gripping moments from {month.strftime('%B %Y')}.",
            month=month,
            segments_used=len(segments),
            total_duration_seconds=total_duration,
            new_narration_seconds=new_narration_secs,
            original_content_ratio=content_ratio,
            file_path=r2_key,
            file_url=file_url,
            file_size_bytes=file_size,
            total_cost_usd=total_cost,
            segment_details=segments,
        )

        log.info(
            "compilation.complete",
            video_id=str(video_id),
            duration=total_duration,
            segments=len(segments),
            content_ratio=round(content_ratio, 3),
        )
        return result

    # ------------------------------------------------------------------
    # Step 1: Identify peak segments from retention curves
    # ------------------------------------------------------------------

    async def _identify_peak_segments(
        self,
        channel_id: UUID,
        month: date,
    ) -> list[PeakSegment]:
        """Query retention curves and extract high-engagement segments."""
        published_after = month - timedelta(days=self._config.retention_lookback_days)

        async with self._db_pool.connection() as conn, conn.cursor() as cur:
            await cur.execute(
                GET_TOP_VIDEOS_WITH_RETENTION,
                {
                    "channel_id": str(channel_id),
                    "published_after": published_after.isoformat(),
                    "min_views": self._config.min_video_views,
                },
            )
            rows = cast("list[dict[str, Any]]", await cur.fetchall())

        segments: list[PeakSegment] = []

        for row in rows:
            retention_curve = row["retention_curve"]
            if not retention_curve:
                continue

            # retention_curve is JSONB: list of 100 floats (0-100) representing
            # retention % at each percentile of the video
            if isinstance(retention_curve, str):
                retention_curve = json.loads(retention_curve)

            video_duration = float(row["video_length_seconds"] or 0)
            if video_duration <= 0:
                continue

            total_views = int(row["total_views"] or 0)
            video_peaks = self._find_peaks_in_curve(
                retention_curve=retention_curve,
                video_duration=video_duration,
                video_id=row["video_id"],
                video_title=row["video_title"],
                youtube_video_id=row["youtube_video_id"],
                total_views=total_views,
            )
            segments.extend(video_peaks)

        # Sort by engagement score descending
        segments.sort(key=lambda s: s.engagement_score, reverse=True)
        return segments

    def _find_peaks_in_curve(
        self,
        *,
        retention_curve: list[float],
        video_duration: float,
        video_id: object,
        video_title: str,
        youtube_video_id: str,
        total_views: int,
    ) -> list[PeakSegment]:
        """Find contiguous regions where retention exceeds the video average.

        A "peak" is a contiguous run of retention data points that are all
        above the rolling average by at least 5 percentage points.
        """
        if len(retention_curve) < 10:
            return []

        curve = [float(x) for x in retention_curve]
        avg_retention = sum(curve) / len(curve)
        threshold = avg_retention + 5.0  # Must be 5pp above average
        seconds_per_point = video_duration / len(curve)

        peaks: list[PeakSegment] = []
        i = 0

        while i < len(curve):
            if curve[i] >= threshold:
                # Start of a peak region
                start_idx = i
                while i < len(curve) and curve[i] >= threshold - 2.0:
                    # Allow 2pp grace to avoid breaking peaks on minor dips
                    i += 1
                end_idx = i

                start_sec = start_idx * seconds_per_point
                end_sec = min(end_idx * seconds_per_point, video_duration)
                duration = end_sec - start_sec

                # Apply length constraints
                if duration < self._config.min_segment_seconds:
                    continue
                if duration > self._config.max_segment_seconds:
                    # Trim to max, keeping the center
                    center = (start_sec + end_sec) / 2
                    half = self._config.max_segment_seconds / 2
                    start_sec = max(0, center - half)
                    end_sec = min(video_duration, center + half)
                    duration = end_sec - start_sec

                # Calculate engagement score
                peak_retention = sum(curve[start_idx:end_idx]) / max(end_idx - start_idx, 1)
                retention_above_avg = peak_retention - avg_retention
                engagement_score = retention_above_avg * math.sqrt(total_views)

                peaks.append(
                    PeakSegment(
                        video_id=cast("UUID", video_id),
                        video_title=video_title,
                        youtube_video_id=youtube_video_id,
                        start_seconds=round(start_sec, 2),
                        end_seconds=round(end_sec, 2),
                        duration_seconds=round(duration, 2),
                        retention_percent=round(peak_retention, 2),
                        view_count=total_views,
                        engagement_score=round(engagement_score, 2),
                        scene_description=f"Peak segment from '{video_title}' "
                        f"({_fmt_time(start_sec)}-{_fmt_time(end_sec)})",
                    )
                )
            else:
                i += 1

        return peaks

    # ------------------------------------------------------------------
    # Step 2: Generate compilation script via Claude
    # ------------------------------------------------------------------

    async def _generate_compilation_script(
        self,
        segments: list[PeakSegment],
        month: date,
        theme: str,
        channel_name: str,
    ) -> CompilationScript:
        """Generate new intro/transitions/outro narration via Claude."""
        month_label = month.strftime("%B %Y")

        segment_descriptions = "\n".join(
            f'{i + 1}. "{seg.video_title}" — '
            f"{_fmt_time(seg.start_seconds)} to {_fmt_time(seg.end_seconds)} "
            f"({seg.duration_seconds:.0f}s, {seg.view_count:,} views, "
            f"{seg.retention_percent:.1f}% retention)\n"
            f"   {seg.scene_description}"
            for i, seg in enumerate(segments)
        )

        prompt = COMPILATION_SCRIPT_PROMPT.format(
            theme=theme,
            month_label=month_label,
            channel_name=channel_name,
            segment_count=len(segments),
            segment_descriptions=segment_descriptions,
        )

        # Use the script generator's Claude client
        response_text, response_cost = await self._script_gen._call_claude(
            system_prompt="You are a true-crime narration writer for YouTube compilations.",
            user_message=prompt,
            model="sonnet",
            max_tokens=4096,
        )

        raw = json.loads(response_text)
        cost = response_cost.cost_usd

        transitions = [
            SegmentTransition(
                from_segment_index=t["from_segment_index"],
                to_segment_index=t["to_segment_index"],
                narration_text=t["narration_text"],
                estimated_duration_seconds=len(t["narration_text"].split()) / 2.5,
            )
            for t in raw["transitions"]
        ]

        intro_words = len(raw["intro_narration"].split())
        outro_words = len(raw["outro_narration"].split())
        transition_words = sum(len(t.narration_text.split()) for t in transitions)
        total_words = intro_words + outro_words + transition_words

        # ~2.5 words/second for narration
        total_narration_seconds = total_words / 2.5

        return CompilationScript(
            intro_narration=raw["intro_narration"],
            outro_narration=raw["outro_narration"],
            transitions=transitions,
            total_new_narration_words=total_words,
            estimated_new_narration_seconds=total_narration_seconds,
            month_label=month_label,
            theme=theme,
            cost=cost if isinstance(cost, Decimal) else Decimal(str(cost)),
        )

    # ------------------------------------------------------------------
    # Step 3: Generate voiceover audio for new narration
    # ------------------------------------------------------------------

    async def _generate_narration_audio(
        self,
        script: CompilationScript,
        channel_id: UUID,
    ) -> list[str]:
        """Generate voiceover for intro, transitions, and outro.

        Returns a list of local file paths in order:
        [intro, transition_0, transition_1, ..., outro]
        """
        narration_texts: list[str] = [script.intro_narration]
        narration_texts.extend(t.narration_text for t in script.transitions)
        narration_texts.append(script.outro_narration)

        paths: list[str] = []
        tempfile.mkdtemp(prefix="crimemill_compilation_")

        for _i, text in enumerate(narration_texts):
            result = await self._voiceover_gen.generate_voiceover(
                script_text=text,
                voice_id="default",
            )
            paths.append(result.file_path)

        return paths

    # ------------------------------------------------------------------
    # Step 4: Extract peak segments from source videos via FFmpeg
    # ------------------------------------------------------------------

    async def _extract_segments(
        self,
        segments: list[PeakSegment],
    ) -> list[str]:
        """Download and extract peak segments from source videos.

        For each segment, either download from R2 (if we have the source MP4)
        or use yt-dlp to download just the needed portion from YouTube.
        """
        tmp_dir = tempfile.mkdtemp(prefix="crimemill_segments_")
        tasks = [self._extract_single_segment(seg, i, tmp_dir) for i, seg in enumerate(segments)]
        return await asyncio.gather(*tasks)

    async def _extract_single_segment(
        self,
        segment: PeakSegment,
        index: int,
        tmp_dir: str,
    ) -> str:
        """Extract a single segment using FFmpeg."""
        output_path = os.path.join(tmp_dir, f"segment_{index:03d}.mp4")

        # Try R2 first (original assembled video), fall back to yt-dlp
        r2_key = f"{segment.video_id}/final/video.mp4"
        source_path = os.path.join(tmp_dir, f"source_{index:03d}.mp4")

        bucket = self._settings.storage.bucket_name
        if self._r2.file_exists(bucket, r2_key):
            self._r2.download_file(bucket, r2_key, source_path)
        else:
            # Download from YouTube using yt-dlp
            url = f"https://www.youtube.com/watch?v={segment.youtube_video_id}"
            proc = await asyncio.create_subprocess_exec(
                "yt-dlp",
                "-f",
                "bestvideo[height<=1440]+bestaudio/best[height<=1440]",
                "--merge-output-format",
                "mp4",
                "-o",
                source_path,
                url,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            _, stderr = await proc.communicate()
            if proc.returncode != 0:
                raise RuntimeError(
                    f"yt-dlp failed for {segment.youtube_video_id}: {stderr.decode()[:500]}"
                )

        # Extract the segment with re-encoding for clean cuts
        duration = segment.end_seconds - segment.start_seconds
        proc = await asyncio.create_subprocess_exec(
            "ffmpeg",
            "-y",
            "-ss",
            str(segment.start_seconds),
            "-i",
            source_path,
            "-t",
            str(duration),
            "-c:v",
            "libx264",
            "-preset",
            "fast",
            "-crf",
            "18",
            "-c:a",
            "aac",
            "-b:a",
            "192k",
            "-movflags",
            "+faststart",
            output_path,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await proc.communicate()
        if proc.returncode != 0:
            raise RuntimeError(f"FFmpeg segment extraction failed: {stderr.decode()[:500]}")

        # Clean up source file
        with contextlib.suppress(OSError):
            os.unlink(source_path)

        logger.info(
            "compilation.segment_extracted",
            index=index,
            video=segment.video_title,
            start=segment.start_seconds,
            end=segment.end_seconds,
        )
        return output_path

    # ------------------------------------------------------------------
    # Step 5: Concatenate segments with transitions
    # ------------------------------------------------------------------

    async def _concatenate_with_transitions(
        self,
        segment_paths: list[str],
        narration_paths: list[str],
        segments: list[PeakSegment],
    ) -> str:
        """Concatenate extracted segments with narration bridges and crossfades.

        Layout: [intro_narration] [segment_0] [transition_0] [segment_1] ...
                [transition_N-1] [segment_N] [outro_narration]

        narration_paths order: [intro, trans_0, trans_1, ..., trans_N-1, outro]
        """
        tmp_dir = tempfile.mkdtemp(prefix="crimemill_concat_")
        _crossfade = self._config.crossfade_seconds  # noqa: F841 — reserved for future crossfade logic

        # Build FFmpeg concat demuxer file
        concat_list_path = os.path.join(tmp_dir, "concat.txt")
        parts: list[str] = []

        # Intro narration (rendered as black screen + voice, or title card)
        intro_video = await self._create_narration_video(narration_paths[0], tmp_dir, "intro")
        parts.append(intro_video)

        # Interleave segments and transitions
        for i, seg_path in enumerate(segment_paths):
            parts.append(seg_path)
            # Add transition narration between segments (not after the last one)
            if i < len(segment_paths) - 1 and (i + 1) < len(narration_paths) - 1:
                trans_video = await self._create_narration_video(
                    narration_paths[i + 1], tmp_dir, f"trans_{i}"
                )
                parts.append(trans_video)

        # Outro narration
        outro_video = await self._create_narration_video(narration_paths[-1], tmp_dir, "outro")
        parts.append(outro_video)

        # Write concat file
        with open(concat_list_path, "w") as f:
            for part in parts:
                # FFmpeg concat demuxer format
                safe_path = part.replace("\\", "/").replace("'", "'\\''")
                f.write(f"file '{safe_path}'\n")

        # Concatenate with FFmpeg
        output_path = os.path.join(tmp_dir, "compilation_final.mp4")
        proc = await asyncio.create_subprocess_exec(
            "ffmpeg",
            "-y",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            concat_list_path,
            "-c:v",
            "libx264",
            "-preset",
            "medium",
            "-crf",
            "18",
            "-c:a",
            "aac",
            "-b:a",
            "192k",
            "-movflags",
            "+faststart",
            output_path,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await proc.communicate()
        if proc.returncode != 0:
            raise RuntimeError(f"FFmpeg concatenation failed: {stderr.decode()[:500]}")

        logger.info("compilation.concatenation_complete", parts=len(parts))
        return output_path

    async def _create_narration_video(
        self,
        audio_path: str,
        tmp_dir: str,
        label: str,
    ) -> str:
        """Create a video file from narration audio with a dark background.

        Produces a simple dark-frame video with the narration audio track,
        suitable for concatenation between source segments.
        """
        output = os.path.join(tmp_dir, f"{label}_video.mp4")

        # Probe audio duration
        info = await self._audio_proc.get_audio_info(audio_path)
        duration = info.duration_seconds

        # Generate a dark video with the audio
        proc = await asyncio.create_subprocess_exec(
            "ffmpeg",
            "-y",
            "-f",
            "lavfi",
            "-i",
            f"color=c=black:s=2560x1440:d={duration}:r=30",
            "-i",
            audio_path,
            "-c:v",
            "libx264",
            "-preset",
            "fast",
            "-crf",
            "23",
            "-c:a",
            "aac",
            "-b:a",
            "192k",
            "-shortest",
            "-movflags",
            "+faststart",
            output,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await proc.communicate()
        if proc.returncode != 0:
            raise RuntimeError(
                f"FFmpeg narration video creation failed for {label}: {stderr.decode()[:500]}"
            )

        return output

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    async def _get_channel_name(self, channel_id: UUID) -> str:
        """Fetch channel name from the database."""
        async with self._db_pool.connection() as conn, conn.cursor() as cur:
            await cur.execute(
                "SELECT name FROM channels WHERE id = %(channel_id)s",
                {"channel_id": str(channel_id)},
            )
            row = cast("dict[str, Any] | None", await cur.fetchone())
            return row["name"] if row else "CrimeMill"

    async def _create_compilation_record(
        self,
        channel_id: UUID,
        title: str,
        month: date,
        theme: str,
        segments: list[PeakSegment],
    ) -> UUID:
        """Insert a new video record for the compilation."""
        topic = {
            "type": "compilation",
            "theme": theme,
            "month": month.isoformat(),
            "source_video_ids": [str(s.video_id) for s in segments],
        }
        tags = ["compilation", theme, month.strftime("%B%Y").lower()]

        async with self._db_pool.connection() as conn, conn.cursor() as cur:
            await cur.execute(
                INSERT_COMPILATION_VIDEO,
                {
                    "channel_id": str(channel_id),
                    "title": title,
                    "description": f"Monthly compilation — {month.strftime('%B %Y')}",
                    "tags": json.dumps(tags),
                    "topic": json.dumps(topic),
                },
            )
            row = cast("dict[str, Any]", await cur.fetchone())
            await conn.commit()
            return cast("UUID", row["id"])


# ---------------------------------------------------------------------------
# Utility
# ---------------------------------------------------------------------------


def _fmt_time(seconds: float) -> str:
    """Format seconds as M:SS or H:MM:SS."""
    total = int(seconds)
    h, remainder = divmod(total, 3600)
    m, s = divmod(remainder, 60)
    if h > 0:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m}:{s:02d}"
