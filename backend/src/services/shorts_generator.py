"""YouTube Shorts generation pipeline.

Produces 2-3 standalone Shorts (9:16, 1080x1920, 30fps) from a finished
long-form video as discovery funnels. Each Short reuses parent images
(no regeneration) and generates fresh voiceover + captions.

Pipeline:
  1. Identify 2-3 best Short-worthy segments via Claude Haiku
  2. Generate TTS voiceover for each segment (Fish Audio)
  3. Transcribe for word-level captions (Groq Whisper)
  4. Build Remotion input props matching ShortProps interface
  5. Render via Remotion Lambda (CrimeShort composition)
  6. Upload rendered Shorts to R2

Key constraints:
  - NO music (halves Shorts revenue)
  - Aggressive Ken Burns (faster zoom/pan than long-form)
  - Word-by-word captions centered at 60% height
  - Hook text overlay first 1-2s, cliffhanger end card last 3-5s
  - 13s or 60s duration targets
  - Optional pipeline stage — failures don't block parent video
"""

from __future__ import annotations

import asyncio
import json
import math
import os
import tempfile
import time
import uuid
from decimal import Decimal
from pathlib import Path
from typing import TYPE_CHECKING, Any

import structlog

from src.models.short import (
    ShortCandidate,
    ShortRenderInput,
    ShortResult,
    ShortsGenerationResult,
)
from src.utils.retry import async_retry
from src.utils.storage import R2Client

if TYPE_CHECKING:
    import httpx

    from src.config import Settings

logger = structlog.get_logger()

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

MODEL_HAIKU = "claude-haiku-4-5-20251001"

# Haiku pricing: $1 / $5 per million tokens
_HAIKU_INPUT_COST_PER_TOKEN = Decimal("0.000001")
_HAIKU_OUTPUT_COST_PER_TOKEN = Decimal("0.000005")

# Ken Burns type rotation for Shorts — same 6 types, different order
# to avoid visual monotony vs long-form
_SHORT_KEN_BURNS_TYPES = [
    "zoom_in",
    "pan_right",
    "pan_down",
    "zoom_out",
    "pan_left",
    "pan_up",
]

# Lambda render cost estimate per Short
_LAMBDA_COST_PER_SHORT = Decimal("0.03")

# Render polling
_POLL_INTERVAL = 3
_RENDER_TIMEOUT = 120  # Shorts are short — render should be fast

_TMP_DIR = Path(tempfile.gettempdir()) / "crimemill" / "shorts"
_TMP_DIR.mkdir(parents=True, exist_ok=True)


# ---------------------------------------------------------------------------
# System prompt for segment identification
# ---------------------------------------------------------------------------

SEGMENT_IDENTIFICATION_PROMPT = """\
You are an expert YouTube Shorts producer for true crime content. Your job is \
to identify the 2-3 most compelling segments from a long-form true crime \
documentary script that would work as standalone YouTube Shorts.

A great Short segment has:
- A STRONG emotional hook in the first 2 seconds (shock, mystery, disbelief)
- Self-contained narrative arc (viewer doesn't need full context)
- A cliffhanger ending that drives viewers to the full video
- High retention potential (viewers watch to the end)

For each segment you MUST provide:
- segment_index (0-based)
- start_time_seconds / end_time_seconds from the original script
- hook_text: bold, punchy text (max 10 words) overlaid in first 1-2s
- cliffhanger_text: drives to full video (max 15 words)
- narration_text: the exact narration for this Short (NOT copied verbatim — \
  adapted for standalone viewing with a new hook opening)
- scene_numbers: which parent scene numbers' images to reuse (list of ints)
- duration_type: "13s" or "60s"
- reasoning: why this segment works

Rules:
- Produce exactly 2 or 3 candidates
- Each segment must be self-contained — a viewer with ZERO context must \
  understand it
- Narration must be rewritten for standalone delivery, NOT a copy-paste
- Hook text must be UPPERCASE, punchy, 3-10 words
- Cliffhanger must reference the full video without being clickbait
- Prefer segments with: reveals, plot twists, shocking evidence, emotional \
  moments, or dramatic confrontations
- Duration: most Shorts should be 60s; only use 13s for single-moment shockers

Respond with a JSON array of candidates. No markdown fences.\
"""


# ---------------------------------------------------------------------------
# ShortsGenerator
# ---------------------------------------------------------------------------


class ShortsGenerator:
    """Generates YouTube Shorts from a finished long-form video.

    Reuses parent images — only generates new voiceover and captions per Short.

    Parameters
    ----------
    settings:
        Application settings (Anthropic key, Fish Audio config, Remotion config).
    http_client:
        Shared async HTTP client.
    """

    def __init__(self, settings: Settings, http_client: httpx.AsyncClient) -> None:
        self._settings = settings
        self._http = http_client
        self._r2 = R2Client(
            account_id=settings.storage.account_id,
            access_key_id=settings.storage.access_key_id,
            secret_access_key=settings.storage.secret_access_key,
        )
        self._bucket = settings.storage.bucket_name

    # ==================================================================
    # Public API
    # ==================================================================

    async def generate_shorts(
        self,
        parent_video_id: uuid.UUID,
        channel_id: uuid.UUID,
        script_text: str,
        scenes: list[dict[str, Any]],
        parent_image_keys: list[str],
    ) -> ShortsGenerationResult:
        """Full Shorts pipeline for one parent video.

        Parameters
        ----------
        parent_video_id:
            UUID of the parent long-form video.
        channel_id:
            Channel UUID for R2 path construction.
        script_text:
            Full parent script text for segment identification.
        scenes:
            Parent scene breakdowns (dicts with scene_number, start/end times).
        parent_image_keys:
            R2 keys for processed parent images, indexed by scene order.

        Returns
        -------
        ShortsGenerationResult
            Aggregate result with all rendered Shorts.
        """
        log = logger.bind(parent_video_id=str(parent_video_id))
        start_time = time.monotonic()
        total_cost = Decimal("0")

        # Step 1: Identify Short-worthy segments
        await log.ainfo("shorts_identifying_segments")
        candidates, id_cost = await self.identify_segments(script_text, scenes)
        total_cost += id_cost

        if not candidates:
            await log.awarn("shorts_no_candidates_found")
            return ShortsGenerationResult(
                parent_video_id=parent_video_id,
                candidates_found=0,
                total_cost_usd=total_cost,
            )

        await log.ainfo(
            "shorts_candidates_found",
            count=len(candidates),
            durations=[c.duration_type for c in candidates],
        )

        # Step 2-5: Process each candidate in parallel
        tasks = [
            self._process_single_short(
                candidate=candidate,
                parent_video_id=parent_video_id,
                channel_id=channel_id,
                parent_image_keys=parent_image_keys,
            )
            for candidate in candidates
        ]
        results_raw = await asyncio.gather(*tasks, return_exceptions=True)

        shorts: list[ShortResult] = []
        for i, result in enumerate(results_raw):
            if isinstance(result, BaseException):
                await log.aerror(
                    "short_failed",
                    segment_index=i,
                    error=str(result),
                )
                continue
            short_result, cost = result
            shorts.append(short_result)
            total_cost += cost

        elapsed = round(time.monotonic() - start_time, 1)
        await log.ainfo(
            "shorts_complete",
            rendered=len(shorts),
            total_cost=str(total_cost),
            elapsed_seconds=elapsed,
        )

        return ShortsGenerationResult(
            parent_video_id=parent_video_id,
            shorts=shorts,
            candidates_found=len(candidates),
            shorts_rendered=len(shorts),
            total_cost_usd=total_cost,
        )

    # ==================================================================
    # Step 1: Segment identification via Claude Haiku
    # ==================================================================

    async def identify_segments(
        self,
        script_text: str,
        scenes: list[dict[str, Any]],
    ) -> tuple[list[ShortCandidate], Decimal]:
        """Use Claude Haiku to find 2-3 best Short-worthy segments.

        Returns
        -------
        tuple
            (list of ShortCandidate, cost in USD)
        """
        # Build scene summary for context
        scene_summary = "\n".join(
            f"Scene {s.get('scene_number', i + 1)}: "
            f"{s.get('start_time_seconds', 0):.0f}s-{s.get('end_time_seconds', 0):.0f}s — "
            f"{s.get('scene_description', s.get('narration_text', ''))[:100]}"
            for i, s in enumerate(scenes)
        )

        user_prompt = (
            f"Here is the full script for a true crime documentary:\n\n"
            f"---SCRIPT START---\n{script_text}\n---SCRIPT END---\n\n"
            f"Scene breakdown:\n{scene_summary}\n\n"
            f"Total scenes: {len(scenes)}\n\n"
            f"Identify 2-3 segments that would make compelling standalone YouTube Shorts."
        )

        response_text, cost = await self._call_haiku(
            system=SEGMENT_IDENTIFICATION_PROMPT,
            user=user_prompt,
        )

        # Parse JSON response
        candidates = self._parse_candidates(response_text)
        return candidates, cost

    # ==================================================================
    # Steps 2-5: Process a single Short
    # ==================================================================

    async def _process_single_short(
        self,
        candidate: ShortCandidate,
        parent_video_id: uuid.UUID,
        channel_id: uuid.UUID,
        parent_image_keys: list[str],
    ) -> tuple[ShortResult, Decimal]:
        """Generate voiceover, captions, and render one Short.

        Returns (ShortResult, total_cost_usd).
        """
        short_id = uuid.uuid4()
        log = logger.bind(
            short_id=str(short_id),
            segment_index=candidate.segment_index,
        )
        cost = Decimal("0")
        start_time = time.monotonic()

        # Step 2: Generate TTS voiceover
        await log.ainfo("short_generating_voiceover")
        audio_path, audio_duration, vo_cost = await self._generate_voiceover(
            short_id,
            candidate.narration_text,
            channel_id,
            parent_video_id,
        )
        cost += vo_cost

        # Step 3: Generate word-level captions via Groq Whisper
        await log.ainfo("short_generating_captions")
        caption_words, cap_cost = await self._generate_captions(
            short_id,
            audio_path,
            channel_id,
            parent_video_id,
        )
        cost += cap_cost

        # Step 4: Build Remotion input props
        fps = 30
        total_frames = math.ceil(audio_duration * fps)

        # Map parent scene images to Short scenes
        short_scenes = self._build_short_scenes(
            candidate.scene_numbers,
            parent_image_keys,
            total_frames,
            channel_id,
            parent_video_id,
            fps,
        )

        # Generate signed audio URL
        audio_r2_key = f"{channel_id}/{parent_video_id}/shorts/{short_id}/voiceover.wav"
        audio_url = self._r2.generate_presigned_url(
            self._bucket,
            audio_r2_key,
            expires_in=7200,
        )

        render_input = ShortRenderInput(
            short_id=short_id,
            parent_video_id=parent_video_id,
            scenes=short_scenes,
            caption_words=caption_words,
            audio_url=audio_url,
            hook_text=candidate.hook_text,
            cliffhanger_text=candidate.cliffhanger_text,
            total_duration_frames=total_frames,
            fps=fps,
        )

        # Step 5: Render via Remotion Lambda
        await log.ainfo("short_rendering", total_frames=total_frames)
        render_result = await self._render_short(
            render_input,
            channel_id,
            parent_video_id,
        )
        cost += _LAMBDA_COST_PER_SHORT

        elapsed = round(time.monotonic() - start_time, 1)

        result = ShortResult(
            short_id=short_id,
            parent_video_id=parent_video_id,
            file_path=render_result["r2_key"],
            file_url=render_result.get("file_url", ""),
            duration_seconds=audio_duration,
            file_size_bytes=render_result.get("file_size_bytes", 0),
            render_time_seconds=elapsed,
            cost_usd=cost,
        )

        await log.ainfo(
            "short_complete",
            duration=audio_duration,
            cost=str(cost),
            elapsed=elapsed,
        )

        return result, cost

    # ==================================================================
    # Voiceover generation (Fish Audio)
    # ==================================================================

    @async_retry(max_attempts=2, base_delay=3.0)
    async def _generate_voiceover(
        self,
        short_id: uuid.UUID,
        narration_text: str,
        channel_id: uuid.UUID,
        parent_video_id: uuid.UUID,
    ) -> tuple[str, float, Decimal]:
        """Generate TTS voiceover for a Short segment.

        Returns (r2_key, duration_seconds, cost_usd).
        """
        from src.services.voiceover_generator import VoiceoverGenerator

        gen = VoiceoverGenerator(self._settings, self._http)
        result = await gen.generate_voiceover(narration_text, "default")

        # Upload to R2 under shorts subfolder
        r2_key = f"{channel_id}/{parent_video_id}/shorts/{short_id}/voiceover.wav"
        await asyncio.to_thread(
            self._r2.upload_file,
            self._bucket,
            r2_key,
            result.file_path,
            "audio/wav",
        )

        return r2_key, result.duration_seconds, result.cost_usd

    # ==================================================================
    # Caption generation (Groq Whisper)
    # ==================================================================

    @async_retry(max_attempts=2, base_delay=2.0)
    async def _generate_captions(
        self,
        short_id: uuid.UUID,
        audio_r2_key: str,
        channel_id: uuid.UUID,
        parent_video_id: uuid.UUID,
    ) -> tuple[list[dict[str, Any]], Decimal]:
        """Transcribe voiceover for word-level caption timing.

        Returns (caption_words as dicts, cost_usd).
        """
        from src.services.caption_generator import CaptionGenerator

        # Download voiceover to temp
        local_path = str(_TMP_DIR / f"{short_id}_vo.wav")
        await asyncio.to_thread(
            self._r2.download_file,
            self._bucket,
            audio_r2_key,
            local_path,
        )

        gen = CaptionGenerator(self._settings, self._http)
        result = await gen.generate_srt(local_path)

        # Convert to Remotion CaptionWord format
        caption_words = [
            {
                "text": w.text,
                "startFrame": w.start_frame,
                "endFrame": w.end_frame,
                "isHighlighted": False,
            }
            for w in result.caption_words
        ]

        # Upload caption data
        words_path = _TMP_DIR / f"{short_id}_caption_words.json"
        words_path.write_text(json.dumps(caption_words), encoding="utf-8")
        words_key = f"{channel_id}/{parent_video_id}/shorts/{short_id}/caption_words.json"
        await asyncio.to_thread(
            self._r2.upload_file,
            self._bucket,
            words_key,
            str(words_path),
            "application/json",
        )

        # Clean up temp
        try:
            os.unlink(local_path)
            os.unlink(str(words_path))
        except OSError:
            pass

        return caption_words, result.cost_usd

    # ==================================================================
    # Remotion Lambda render
    # ==================================================================

    async def _render_short(
        self,
        input: ShortRenderInput,
        channel_id: uuid.UUID,
        parent_video_id: uuid.UUID,
    ) -> dict[str, Any]:
        """Render a Short via Remotion Lambda.

        Uses the CrimeShort composition (1080x1920, 9:16).
        Returns dict with r2_key and metadata.
        """
        # Build Remotion input props matching ShortProps interface
        input_props = {
            "scenes": input.scenes,
            "captionWords": input.caption_words,
            "audioUrl": input.audio_url,
            "hookText": input.hook_text,
            "cliffhangerText": input.cliffhanger_text,
            "totalDurationFrames": input.total_duration_frames,
            "fps": input.fps,
        }

        # Write props to temp file for the render script
        props_path = _TMP_DIR / f"{input.short_id}_props.json"
        props_path.write_text(json.dumps(input_props), encoding="utf-8")

        # Trigger Remotion Lambda render via Node.js bridge
        script_path = self._settings.remotion.render_script_path

        env = {
            **os.environ,
            "REMOTION_AWS_ACCESS_KEY_ID": self._settings.remotion.aws_access_key_id,
            "REMOTION_AWS_SECRET_ACCESS_KEY": self._settings.remotion.aws_secret_access_key,
            "REMOTION_AWS_REGION": self._settings.remotion.aws_region,
            "REMOTION_LAMBDA_FUNCTION_NAME": self._settings.remotion.lambda_function_name,
            "REMOTION_SERVE_URL": self._settings.remotion.serve_url,
            "REMOTION_COMPOSITION_ID": "CrimeShort",
            "RENDER_VIDEO_ID": str(input.short_id),
        }

        proc = await asyncio.create_subprocess_exec(
            "npx",
            "tsx",
            script_path,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env,
        )

        stdout, stderr = await proc.communicate(input=json.dumps(input_props).encode())

        if proc.returncode != 0:
            error_msg = stderr.decode().strip()
            raise RuntimeError(f"Short render failed (exit {proc.returncode}): {error_msg[:500]}")

        render_result = json.loads(stdout.decode().strip())
        render_id = render_result.get("renderId", "")

        # Poll for completion
        output_url = await self._poll_render(render_id)

        # Download rendered Short from S3
        local_mp4 = str(_TMP_DIR / f"{input.short_id}.mp4")
        async with self._http.stream("GET", output_url, timeout=120.0) as resp:
            resp.raise_for_status()
            with open(local_mp4, "wb") as f:
                async for chunk in resp.aiter_bytes(chunk_size=65536):
                    f.write(chunk)

        file_size = os.path.getsize(local_mp4)

        # Upload to R2
        r2_key = f"{channel_id}/{parent_video_id}/shorts/{input.short_id}/short.mp4"
        await asyncio.to_thread(
            self._r2.upload_file,
            self._bucket,
            r2_key,
            local_mp4,
            "video/mp4",
        )

        file_url = f"{self._settings.storage.public_url}/{r2_key}"

        # Clean up
        try:
            os.unlink(local_mp4)
            os.unlink(str(props_path))
        except OSError:
            pass

        return {
            "r2_key": r2_key,
            "file_url": file_url,
            "file_size_bytes": file_size,
            "render_id": render_id,
        }

    async def _poll_render(self, render_id: str) -> str:
        """Poll Remotion Lambda for Short render completion.

        Returns the output S3 URL when done.
        """
        script_path = self._settings.remotion.render_script_path
        env = {
            **os.environ,
            "REMOTION_AWS_ACCESS_KEY_ID": self._settings.remotion.aws_access_key_id,
            "REMOTION_AWS_SECRET_ACCESS_KEY": self._settings.remotion.aws_secret_access_key,
            "REMOTION_AWS_REGION": self._settings.remotion.aws_region,
            "REMOTION_LAMBDA_FUNCTION_NAME": self._settings.remotion.lambda_function_name,
            "REMOTION_SERVE_URL": self._settings.remotion.serve_url,
        }

        deadline = time.monotonic() + _RENDER_TIMEOUT

        while time.monotonic() < deadline:
            proc = await asyncio.create_subprocess_exec(
                "npx",
                "tsx",
                script_path,
                "--status",
                render_id,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=env,
            )
            stdout, _ = await proc.communicate()

            if proc.returncode == 0:
                data = json.loads(stdout.decode().strip())
                status = data.get("status", "")

                if status == "done":
                    output_url: str = data.get("outputUrl", "")
                    if output_url:
                        return output_url
                    raise RuntimeError(f"Render done but no outputUrl: {data}")

                if status == "error":
                    raise RuntimeError(f"Short render error: {data.get('errorMessage', 'unknown')}")

            await asyncio.sleep(_POLL_INTERVAL)

        raise TimeoutError(f"Short render {render_id} timed out after {_RENDER_TIMEOUT}s")

    # ==================================================================
    # Scene building
    # ==================================================================

    def _build_short_scenes(
        self,
        scene_numbers: list[int],
        parent_image_keys: list[str],
        total_frames: int,
        channel_id: uuid.UUID,
        parent_video_id: uuid.UUID,
        fps: int = 30,
    ) -> list[dict[str, Any]]:
        """Build ShortScene props for Remotion from parent images.

        Distributes frames evenly across the selected scenes.
        Uses aggressive Ken Burns rotation.
        """
        if not scene_numbers:
            scene_numbers = [0]

        # Resolve image keys — scene_numbers are 1-based from the parent
        image_keys: list[str] = []
        for sn in scene_numbers:
            idx = sn - 1  # convert to 0-based
            if 0 <= idx < len(parent_image_keys):
                image_keys.append(parent_image_keys[idx])
            elif parent_image_keys:
                # Fallback to last available image
                image_keys.append(parent_image_keys[-1])

        if not image_keys:
            return []

        # Distribute frames evenly
        n = len(image_keys)
        base_frames = total_frames // n
        remainder = total_frames % n

        scenes: list[dict[str, Any]] = []
        current_frame = 0

        for i, key in enumerate(image_keys):
            dur = base_frames + (1 if i < remainder else 0)
            kb_type = _SHORT_KEN_BURNS_TYPES[i % len(_SHORT_KEN_BURNS_TYPES)]

            # Generate signed URL for Remotion Lambda to download
            image_url = self._r2.generate_presigned_url(
                self._bucket,
                key,
                expires_in=7200,
            )

            scenes.append(
                {
                    "imageUrl": image_url,
                    "startFrame": current_frame,
                    "durationFrames": dur,
                    "kenBurnsType": kb_type,
                }
            )
            current_frame += dur

        return scenes

    # ==================================================================
    # Claude Haiku helper
    # ==================================================================

    @async_retry(max_attempts=2, base_delay=2.0)
    async def _call_haiku(
        self,
        system: str,
        user: str,
    ) -> tuple[str, Decimal]:
        """Call Claude Haiku and return (response_text, cost_usd)."""
        response = await self._http.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": self._settings.anthropic.api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={
                "model": MODEL_HAIKU,
                "max_tokens": 4096,
                "system": [
                    {
                        "type": "text",
                        "text": system,
                        "cache_control": {"type": "ephemeral"},
                    }
                ],
                "messages": [{"role": "user", "content": user}],
            },
            timeout=60.0,
        )
        response.raise_for_status()
        data = response.json()

        text = ""
        for block in data.get("content", []):
            if block.get("type") == "text":
                text += block["text"]

        usage = data.get("usage", {})
        input_tokens = usage.get("input_tokens", 0)
        output_tokens = usage.get("output_tokens", 0)
        cost = (
            Decimal(input_tokens) * _HAIKU_INPUT_COST_PER_TOKEN
            + Decimal(output_tokens) * _HAIKU_OUTPUT_COST_PER_TOKEN
        )

        return text, cost

    # ==================================================================
    # Parsing helpers
    # ==================================================================

    @staticmethod
    def _parse_candidates(response_text: str) -> list[ShortCandidate]:
        """Parse Claude's JSON response into ShortCandidate objects."""
        # Strip any markdown fences
        text = response_text.strip()
        if text.startswith("```"):
            lines = text.split("\n")
            lines = [line for line in lines if not line.strip().startswith("```")]
            text = "\n".join(lines).strip()

        try:
            raw = json.loads(text)
        except json.JSONDecodeError:
            logger.warning("shorts_parse_failed", response=text[:200])
            return []

        if not isinstance(raw, list):
            raw = [raw]

        candidates: list[ShortCandidate] = []
        for i, item in enumerate(raw):
            try:
                item["segment_index"] = i
                candidates.append(ShortCandidate.model_validate(item))
            except Exception as e:
                logger.warning(
                    "shorts_candidate_invalid",
                    index=i,
                    error=str(e),
                )

        return candidates
