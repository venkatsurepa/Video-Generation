"""Video assembly service — orchestrates Remotion Lambda rendering.

Bridges the Python backend to the Remotion TypeScript renderer by:
1. Building input props that match video/src/types.ts VideoProps exactly
2. Invoking a thin Node.js wrapper script (scripts/render_video.ts) that calls
   the @remotion/lambda renderMediaOnLambda API
3. Polling for render completion (typically 56-61s for a 10-min video)
4. Downloading the rendered MP4 from Remotion's S3 output bucket
5. Uploading the final video to R2 for long-term storage

Remotion Lambda setup requirements (one-time):
  - AWS account with Lambda enabled in the target region
  - `cd video && npx remotion lambda sites create src/index.ts --site-name crimemill`
    → produces REMOTION_SERVE_URL
  - `npx remotion lambda functions deploy --memory 2048 --timeout 300`
    → produces REMOTION_LAMBDA_FUNCTION_NAME
  - Environment variables:
      REMOTION_AWS_ACCESS_KEY_ID     — IAM key with Lambda + S3 permissions
      REMOTION_AWS_SECRET_ACCESS_KEY — corresponding secret
      REMOTION_AWS_REGION            — e.g. us-east-1
      REMOTION_LAMBDA_FUNCTION_NAME  — deployed Lambda function name
      REMOTION_SERVE_URL             — deployed Remotion site URL

Output encoding spec (for YouTube VP9 trigger):
  - 2560×1440 (1440p)
  - H.264 High Profile, CRF 18
  - AAC-LC 48 kHz
  - yuv420p pixel format
  - -movflags +faststart

Cost: ~$0.10-0.11 per 10-minute video render on Lambda.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import math
import os
import tempfile
import time
from decimal import Decimal
from pathlib import Path
from typing import TYPE_CHECKING, Any

import structlog

from src.models.assembly import (
    AssemblyInput,
    AssemblyResult,
    RenderStatus,
    SceneForAssembly,
)
from src.utils.retry import async_retry
from src.utils.storage import R2Client

if TYPE_CHECKING:
    import httpx

    from src.config import Settings

logger = structlog.get_logger()

# ---------------------------------------------------------------------------
# Ken Burns rotation — 6 types, deterministic, never-repeat consecutive
# ---------------------------------------------------------------------------

KEN_BURNS_TYPES = [
    "zoom_in",
    "pan_right",
    "zoom_out",
    "pan_left",
    "pan_up",
    "pan_down",
]

# Remotion Lambda cost estimate per invocation (us-east-1, 2048 MB, ~60s)
_LAMBDA_COST_PER_RENDER = Decimal("0.105")

# Polling configuration
_POLL_INTERVAL_SECONDS = 5
_DEFAULT_RENDER_TIMEOUT = 300  # 5 minutes

# Output video path template in R2
_R2_VIDEO_KEY_TEMPLATE = "videos/{video_id}/final.mp4"

# Render script location relative to the repository root
_RENDER_SCRIPT_DEFAULT = "video/scripts/render_video.ts"


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class RenderError(Exception):
    """Raised when a Remotion Lambda render fails."""

    def __init__(self, render_id: str, message: str) -> None:
        self.render_id = render_id
        super().__init__(f"Render {render_id} failed: {message}")


class RenderTimeoutError(RenderError):
    """Raised when a render exceeds the configured timeout."""


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------


class VideoAssembler:
    """Assembles the final video using Remotion Lambda.

    Prepares input props from all generated assets and triggers
    a Remotion render via a Node.js bridge script to produce the final MP4.
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
        self._tmp_dir = Path(tempfile.gettempdir()) / "crimemill" / "renders"
        self._tmp_dir.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def render(self, input: AssemblyInput) -> AssemblyResult:
        """Full render workflow.

        1. Build Remotion input props from AssemblyInput
        2. Trigger Lambda render via Node.js bridge script
        3. Poll for render completion (typically 56-61 seconds for 10-min video)
        4. Download rendered MP4 from S3
        5. Upload to R2 for persistent storage
        6. Verify output (file size, duration)
        7. Return result with file path and metadata
        """
        start_time = time.monotonic()
        video_id = str(input.video_id)

        await logger.ainfo(
            "render_start",
            video_id=video_id,
            title=input.title,
            scene_count=len(input.scenes),
            caption_word_count=len(input.caption_words),
            audio_duration=input.audio_duration_seconds,
        )

        # 1. Build input props
        input_props = self.build_input_props(input)

        # 2. Trigger Lambda render
        render_id = await self.trigger_lambda_render(input_props, video_id)

        await logger.ainfo("render_triggered", video_id=video_id, render_id=render_id)

        # 3. Poll for completion
        timeout = self._settings.remotion.render_timeout_ms // 1000
        status = await self.poll_render_status(render_id, timeout_seconds=timeout)

        if status.status == "error":
            raise RenderError(render_id, status.error_message or "Unknown error")

        assert status.output_url is not None  # noqa: S101

        await logger.ainfo(
            "render_complete",
            video_id=video_id,
            render_id=render_id,
            output_url=status.output_url,
        )

        # 4. Download rendered MP4 from S3
        local_path = await self.download_rendered_video(
            s3_url=status.output_url,
            destination=str(self._tmp_dir / f"{video_id}.mp4"),
        )

        # 5. Verify output
        file_size = os.path.getsize(local_path)
        if file_size == 0:
            raise RenderError(render_id, "Rendered video has zero bytes")

        # 6. Upload to R2
        r2_key = _R2_VIDEO_KEY_TEMPLATE.format(video_id=video_id)
        await asyncio.to_thread(
            self._r2.upload_file,
            self._bucket,
            r2_key,
            local_path,
            "video/mp4",
        )

        file_url = f"{self._settings.storage.public_url}/{r2_key}"
        render_time = time.monotonic() - start_time

        await logger.ainfo(
            "assembly_complete",
            video_id=video_id,
            render_id=render_id,
            file_size_bytes=file_size,
            render_time_seconds=round(render_time, 1),
            r2_key=r2_key,
        )

        # Clean up temp file
        with contextlib.suppress(OSError):
            os.unlink(local_path)

        return AssemblyResult(
            file_path=r2_key,
            file_url=file_url,
            youtube_ready=True,
            duration_seconds=input.audio_duration_seconds,
            resolution=f"{input.resolution[0]}x{input.resolution[1]}",
            file_size_bytes=file_size,
            codec="h264",
            render_time_seconds=round(render_time, 1),
            cost_usd=_LAMBDA_COST_PER_RENDER,
            render_id=render_id,
        )

    # ------------------------------------------------------------------
    # Input prop building
    # ------------------------------------------------------------------

    def build_input_props(self, input: AssemblyInput) -> dict[str, Any]:
        """Convert AssemblyInput to Remotion's expected input props JSON.

        Must match video/src/types.ts VideoProps interface exactly:
        {
            title: string,
            fps: number,
            totalDurationFrames: number,
            audioUrl: string,
            musicUrl: string,
            scenes: SceneProps[],
            captionWords: CaptionWord[]
        }
        """
        fps = input.fps
        total_duration_frames = math.ceil(input.audio_duration_seconds * fps)

        # Generate signed URLs for all assets (2-hour expiry for render + retry)
        scene_image_urls = self._generate_signed_urls(
            [(s.image_storage_path, "image/jpeg") for s in input.scenes],
            expiry=7200,
        )
        audio_url = self._r2.generate_presigned_url(self._bucket, input.audio_path, expires_in=7200)
        music_url = ""
        if input.music_path:
            music_url = self._r2.generate_presigned_url(
                self._bucket, input.music_path, expires_in=7200
            )

        # Calculate scene frames and assign Ken Burns types
        scene_frames = self._calculate_scene_frames(input.scenes, fps)
        kb_types = self._assign_ken_burns_types(len(input.scenes))

        # Build scenes array matching SceneProps interface
        scenes: list[dict[str, Any]] = []
        for i, scene in enumerate(input.scenes):
            scenes.append(
                {
                    "imageUrl": scene_image_urls[i],
                    "startFrame": scene_frames[i]["start_frame"],
                    "durationFrames": scene_frames[i]["duration_frames"],
                    "kenBurnsType": kb_types[i],
                    "narrationText": scene.narration_text,
                }
            )

        # Build captionWords array matching CaptionWord interface
        # The caption_words from upstream already have frame timing,
        # but we need to map to the camelCase keys Remotion expects.
        caption_words: list[dict[str, Any]] = [
            {
                "text": w.text,
                "startFrame": w.start_frame,
                "endFrame": w.end_frame,
                "isHighlighted": False,
            }
            for w in input.caption_words
        ]

        return {
            "title": input.title,
            "fps": fps,
            "totalDurationFrames": total_duration_frames,
            "audioUrl": audio_url,
            "musicUrl": music_url,
            "scenes": scenes,
            "captionWords": caption_words,
        }

    # ------------------------------------------------------------------
    # Lambda render trigger via Node.js bridge
    # ------------------------------------------------------------------

    async def trigger_lambda_render(self, input_props: dict[str, Any], video_id: str) -> str:
        """Trigger Remotion Lambda render via the Node.js bridge script.

        Since the @remotion/lambda API is Node.js-only, we shell out to a
        thin TypeScript wrapper at scripts/render_video.ts that:
        1. Accepts input props JSON from stdin
        2. Calls renderMediaOnLambda with our config
        3. Prints a JSON result to stdout: {"renderId": "...", "bucketName": "..."}

        Returns the render ID for polling.
        """
        script_path = self._settings.remotion.render_script_path

        # Pass Remotion config via environment variables so the script can
        # read them without us embedding secrets in the JSON payload.
        env = {
            **os.environ,
            "REMOTION_AWS_ACCESS_KEY_ID": self._settings.remotion.aws_access_key_id,
            "REMOTION_AWS_SECRET_ACCESS_KEY": self._settings.remotion.aws_secret_access_key,
            "REMOTION_AWS_REGION": self._settings.remotion.aws_region,
            "REMOTION_LAMBDA_FUNCTION_NAME": self._settings.remotion.lambda_function_name,
            "REMOTION_SERVE_URL": self._settings.remotion.serve_url,
            "REMOTION_FRAMES_PER_LAMBDA": str(self._settings.remotion.frames_per_lambda),
            "REMOTION_RENDER_TIMEOUT_MS": str(self._settings.remotion.render_timeout_ms),
            "RENDER_VIDEO_ID": video_id,
        }

        props_json = json.dumps(input_props)

        await logger.ainfo(
            "trigger_lambda",
            video_id=video_id,
            script=script_path,
            props_size_bytes=len(props_json),
        )

        proc = await asyncio.create_subprocess_exec(
            "npx",
            "tsx",
            script_path,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env,
        )

        stdout, stderr = await proc.communicate(input=props_json.encode())

        if proc.returncode != 0:
            error_msg = stderr.decode().strip()
            await logger.aerror(
                "render_trigger_failed",
                video_id=video_id,
                returncode=proc.returncode,
                stderr=error_msg[:1000],
            )
            raise RenderError(
                render_id="",
                message=f"Render script exited with code {proc.returncode}: {error_msg[:500]}",
            )

        # Parse the JSON output from the script
        try:
            result = json.loads(stdout.decode().strip())
        except json.JSONDecodeError as e:
            raise RenderError(
                render_id="",
                message=f"Failed to parse render script output: {e}",
            ) from e

        render_id: str = result.get("renderId", "")
        if not render_id:
            raise RenderError(render_id="", message=f"No renderId in script output: {result}")

        return render_id

    # ------------------------------------------------------------------
    # Render status polling
    # ------------------------------------------------------------------

    async def poll_render_status(
        self, render_id: str, timeout_seconds: int = _DEFAULT_RENDER_TIMEOUT
    ) -> RenderStatus:
        """Poll Remotion Lambda for render completion.

        Renders typically complete in 56-61 seconds for a 10-minute video.
        Polls every 5 seconds via the Node.js bridge script.

        Returns RenderStatus with final state (done or error).
        """
        deadline = time.monotonic() + timeout_seconds

        while time.monotonic() < deadline:
            status = await self._check_render_progress(render_id)

            if status.status == "done":
                return status

            if status.status == "error":
                return status

            pct = round(status.progress * 100)
            await logger.ainfo(
                "render_progress",
                render_id=render_id,
                progress=f"{pct}%",
            )

            await asyncio.sleep(_POLL_INTERVAL_SECONDS)

        raise RenderTimeoutError(
            render_id=render_id,
            message=f"Render timed out after {timeout_seconds}s",
        )

    async def _check_render_progress(self, render_id: str) -> RenderStatus:
        """Check render progress via the Node.js bridge script.

        Invokes: npx tsx scripts/render_video.ts --status <render_id>
        Expects JSON: {"status": "rendering"|"done"|"error", "progress": 0.0-1.0,
                        "outputUrl": "...", "errorMessage": "..."}
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

        stdout, stderr = await proc.communicate()

        if proc.returncode != 0:
            error_msg = stderr.decode().strip()
            return RenderStatus(
                render_id=render_id,
                status="error",
                progress=0.0,
                error_message=f"Status check failed: {error_msg[:500]}",
            )

        try:
            data = json.loads(stdout.decode().strip())
        except json.JSONDecodeError:
            return RenderStatus(
                render_id=render_id,
                status="error",
                progress=0.0,
                error_message="Failed to parse status response",
            )

        return RenderStatus(
            render_id=render_id,
            status=data.get("status", "error"),
            progress=float(data.get("progress", 0.0)),
            output_url=data.get("outputUrl"),
            error_message=data.get("errorMessage"),
        )

    # ------------------------------------------------------------------
    # Download rendered video
    # ------------------------------------------------------------------

    @async_retry(max_attempts=3, base_delay=2.0)
    async def download_rendered_video(self, s3_url: str, destination: str) -> str:
        """Download the rendered MP4 from Remotion's S3 output bucket.

        Verifies:
        - File exists and size > 0
        - Download completes successfully

        Returns local file path.
        """
        await logger.ainfo("download_video", url=s3_url[:120], destination=destination)

        async with self._http.stream("GET", s3_url, timeout=300.0) as resp:
            resp.raise_for_status()
            with open(destination, "wb") as f:
                async for chunk in resp.aiter_bytes(chunk_size=65536):
                    f.write(chunk)

        file_size = os.path.getsize(destination)
        if file_size == 0:
            raise ValueError(f"Downloaded file is empty: {destination}")

        await logger.ainfo(
            "download_complete",
            destination=destination,
            file_size_bytes=file_size,
        )
        return destination

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _calculate_scene_frames(
        self, scenes: list[SceneForAssembly], fps: int = 30
    ) -> list[dict[str, int]]:
        """Convert scene timestamps (seconds) to frame numbers.

        Handles rounding to ensure scenes tile perfectly with no gaps.
        Each scene: start_frame = round(start_seconds × fps)
                    duration_frames = next_start_frame - start_frame
        Last scene extends to the end of its specified time.
        """
        result: list[dict[str, int]] = []

        for i, scene in enumerate(scenes):
            start_frame = round(scene.start_seconds * fps)

            if i + 1 < len(scenes):
                # Next scene's start determines this scene's end — no gaps
                next_start_frame = round(scenes[i + 1].start_seconds * fps)
                duration_frames = next_start_frame - start_frame
            else:
                # Last scene: use its own end time
                end_frame = round(scene.end_seconds * fps)
                duration_frames = end_frame - start_frame

            # Ensure minimum 1 frame duration
            duration_frames = max(duration_frames, 1)

            result.append(
                {
                    "start_frame": start_frame,
                    "duration_frames": duration_frames,
                }
            )

        return result

    def _assign_ken_burns_types(self, scene_count: int) -> list[str]:
        """Assign Ken Burns movement types to scenes.

        Cycles through: zoom_in, pan_right, zoom_out, pan_left, pan_up, pan_down
        Deterministic rotation based on scene index — never repeats consecutively.
        """
        types: list[str] = []
        for i in range(scene_count):
            kb_type = KEN_BURNS_TYPES[i % len(KEN_BURNS_TYPES)]

            # Guard against consecutive repeat (shouldn't happen with 6-cycle,
            # but protects against edge cases with very few scenes)
            if types and kb_type == types[-1]:
                kb_type = KEN_BURNS_TYPES[(i + 1) % len(KEN_BURNS_TYPES)]

            types.append(kb_type)

        return types

    def _generate_signed_urls(self, paths: list[tuple[str, str]], expiry: int = 7200) -> list[str]:
        """Generate R2 presigned URLs for all assets.

        Remotion Lambda needs to download images and audio during render,
        so all R2 paths must be converted to publicly accessible signed URLs.
        Expiry defaults to 2 hours — generous for render + retry window.
        """
        urls: list[str] = []
        for storage_path, _content_type in paths:
            url = self._r2.generate_presigned_url(self._bucket, storage_path, expires_in=expiry)
            urls.append(url)
        return urls
