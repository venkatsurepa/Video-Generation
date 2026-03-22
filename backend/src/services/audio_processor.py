from __future__ import annotations

import asyncio
import json
import os
import re
import shutil
import tempfile
from typing import TYPE_CHECKING

import structlog

if TYPE_CHECKING:
    import httpx

    from src.config import Settings
    from src.models.audio import AudioInfo, AudioResult, SFXCue, SilenceMarker

logger = structlog.get_logger()


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class FFmpegError(Exception):
    """Raised when an FFmpeg command exits with a non-zero code."""

    def __init__(self, command: str, returncode: int, stderr: str) -> None:
        self.command = command
        self.returncode = returncode
        self.stderr = stderr
        super().__init__(f"FFmpeg failed (code {returncode}): {stderr[:500]}")


class FFmpegNotFoundError(Exception):
    """Raised when ffmpeg or ffprobe is not found in PATH."""


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------


class AudioProcessor:
    """Audio post-processing service for the CrimeMill pipeline.

    Handles ALL audio work between raw TTS output and final video assembly:
    voiceover EQ, auto-ducking, SFX overlay, loudness normalization, and
    final mix.  Wraps FFmpeg (async subprocess) and pydub.
    """

    # Crime-documentary voiceover EQ chain (single FFmpeg -af string).
    #   HPF 80 Hz  → remove rumble
    #   +1.5 dB @ 100 Hz  → chest warmth
    #   -2.5 dB @ 250 Hz  → mud cut
    #   +2.5 dB @ 5 kHz   → clarity / presence
    #   LPF 10 kHz → darker crime tone
    #   compand  → gentle 2:1 compression with soft knee
    _VOICE_EQ_CHAIN = ",".join(
        [
            "highpass=f=80",
            "equalizer=f=100:t=q:w=1:g=1.5",
            "equalizer=f=250:t=q:w=1:g=-2.5",
            "equalizer=f=5000:t=q:w=1:g=2.5",
            "lowpass=f=10000",
            (
                "compand=attacks=0.3:decays=0.8"
                ":points=-80/-80|-45/-45|-27/-25|-20/-15"
                ":soft-knee=6:gain=0"
            ),
        ]
    )

    # Sidechain-compress filter for auto-ducking music under narration.
    _DUCK_FILTER = (
        "[1:a]apad[music];"
        "[music][0:a]sidechaincompress="
        "threshold=0.03:ratio=4:attack=200:release=1000[ducked];"
        "[0:a][ducked]amix=inputs=2:duration=first:dropout_transition=3"
    )

    def __init__(self, settings: Settings, http_client: httpx.AsyncClient) -> None:
        self._settings = settings
        self._http = http_client
        self._ffmpeg_verified = False

    # ------------------------------------------------------------------
    # FFmpeg / FFprobe helpers
    # ------------------------------------------------------------------

    async def _ensure_ffmpeg(self) -> None:
        """Verify that ffmpeg and ffprobe are reachable.  Cached after the
        first successful check so subsequent calls are free.
        """
        if self._ffmpeg_verified:
            return
        for binary in ("ffmpeg", "ffprobe"):
            try:
                proc = await asyncio.create_subprocess_exec(
                    binary,
                    "-version",
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                await proc.communicate()
                if proc.returncode != 0:
                    raise FFmpegNotFoundError(f"{binary} returned exit code {proc.returncode}")
            except FileNotFoundError:
                raise FFmpegNotFoundError(
                    f"{binary} not found in PATH. Install FFmpeg: https://ffmpeg.org/download.html"
                ) from None
        self._ffmpeg_verified = True
        await logger.ainfo("ffmpeg_verified")

    async def _run_ffmpeg(self, *args: str) -> str:
        """Execute an FFmpeg command asynchronously.

        Always passes ``-y`` (overwrite) and ``-hide_banner``.
        Returns the captured *stderr* (which contains progress and
        measurement output).  Raises :class:`FFmpegError` on non-zero exit.
        """
        await self._ensure_ffmpeg()
        cmd = ["ffmpeg", "-y", "-hide_banner", *args]
        await logger.ainfo("ffmpeg_exec", cmd=" ".join(cmd))
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr_bytes = await proc.communicate()
        stderr = stderr_bytes.decode("utf-8", errors="replace")
        if proc.returncode != 0:
            await logger.aerror(
                "ffmpeg_failed",
                returncode=proc.returncode,
                stderr=stderr[:500],
            )
            raise FFmpegError(
                command=" ".join(cmd),
                returncode=proc.returncode,
                stderr=stderr,
            )
        return stderr

    async def _run_ffprobe(self, *args: str) -> str:
        """Execute an FFprobe command asynchronously.  Returns *stdout*."""
        await self._ensure_ffmpeg()
        cmd = ["ffprobe", *args]
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout_bytes, stderr_bytes = await proc.communicate()
        if proc.returncode != 0:
            stderr = stderr_bytes.decode("utf-8", errors="replace")
            raise FFmpegError(
                command=" ".join(cmd),
                returncode=proc.returncode,
                stderr=stderr,
            )
        return stdout_bytes.decode("utf-8", errors="replace")

    # ------------------------------------------------------------------
    # Internal utilities
    # ------------------------------------------------------------------

    async def _build_audio_result(self, output_path: str) -> AudioResult:
        """Probe *output_path* and return a populated :class:`AudioResult`."""
        from src.models.audio import AudioResult

        info = await self.get_audio_info(output_path)
        return AudioResult(
            output_path=output_path,
            duration_seconds=info.duration_seconds,
            sample_rate=info.sample_rate,
            file_size_bytes=info.file_size_bytes,
        )

    @staticmethod
    def _parse_loudnorm_stats(stderr: str) -> dict[str, str]:
        """Extract the loudnorm measurement JSON from FFmpeg stderr.

        The ``loudnorm`` filter with ``print_format=json`` emits a JSON
        object as the last ``{…}`` block in stderr.
        """
        matches = list(re.finditer(r"\{[^{}]+\}", stderr, re.DOTALL))
        if not matches:
            raise FFmpegError(
                command="loudnorm measurement",
                returncode=0,
                stderr="No loudnorm JSON block found in FFmpeg output",
            )
        raw = matches[-1].group()
        try:
            stats: dict[str, str] = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise FFmpegError(
                command="loudnorm measurement",
                returncode=0,
                stderr=f"Failed to parse loudnorm JSON: {raw[:200]}",
            ) from exc
        required = (
            "input_i",
            "input_tp",
            "input_lra",
            "input_thresh",
            "target_offset",
        )
        missing = [k for k in required if k not in stats]
        if missing:
            raise FFmpegError(
                command="loudnorm measurement",
                returncode=0,
                stderr=f"Missing required loudnorm keys: {missing}",
            )
        return stats

    # ------------------------------------------------------------------
    # pydub helpers (sync, run via asyncio.to_thread)
    # ------------------------------------------------------------------

    @staticmethod
    def _overlay_sfx_sync(
        base_path: str,
        sfx_cues: list[SFXCue],
        output_path: str,
    ) -> None:
        """Overlay SFX cues onto a base track using pydub (blocking)."""
        from pydub import AudioSegment

        base = AudioSegment.from_file(base_path)
        for cue in sfx_cues:
            sfx = AudioSegment.from_file(cue.file_path)
            sfx = sfx + cue.volume_db  # dB gain/attenuation

            # Ambient beds loop to fill the requested duration.
            if cue.cue_type == "ambient_bed" and cue.duration_seconds is not None:
                target_ms = int(cue.duration_seconds * 1000)
                if len(sfx) > 0:
                    repeats = (target_ms // len(sfx)) + 1
                    sfx = (sfx * repeats)[:target_ms]

            position_ms = int(cue.timestamp_seconds * 1000)
            base = base.overlay(sfx, position=position_ms)

        base.export(output_path, format="wav")

    @staticmethod
    def _add_silence_sync(
        input_path: str,
        positions: list[SilenceMarker],
        output_path: str,
    ) -> None:
        """Insert silence gaps into audio at given positions (blocking).

        Positions are processed in reverse so earlier insertions don't
        shift later timestamps.
        """
        from pydub import AudioSegment

        audio = AudioSegment.from_file(input_path)
        for marker in sorted(positions, key=lambda m: m.position_seconds, reverse=True):
            pos_ms = int(marker.position_seconds * 1000)
            gap = AudioSegment.silent(duration=int(marker.duration_seconds * 1000))
            audio = audio[:pos_ms] + gap + audio[pos_ms:]

        audio.export(output_path, format="wav")

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def process_voiceover(self, input_path: str, output_path: str) -> AudioResult:
        """Apply the crime-documentary EQ chain to a raw TTS voiceover.

        Pipeline (single FFmpeg ``-af`` filter graph):
            HPF 80 Hz → +1.5 dB @ 100 Hz → −2.5 dB @ 250 Hz →
            +2.5 dB @ 5 kHz → LPF 10 kHz → compand (2 : 1)

        Output: 48 kHz, 24-bit WAV.
        """
        await self._run_ffmpeg(
            "-i",
            input_path,
            "-af",
            self._VOICE_EQ_CHAIN,
            "-ar",
            "48000",
            "-c:a",
            "pcm_s24le",
            output_path,
        )
        await logger.ainfo(
            "voiceover_processed",
            input=input_path,
            output=output_path,
        )
        return await self._build_audio_result(output_path)

    async def duck_music_under_voice(
        self, voice_path: str, music_path: str, output_path: str
    ) -> AudioResult:
        """Auto-duck a music track under narration via sidechain compression.

        Music is reduced −15 to −25 dB while the narrator is speaking.
        Sidechain parameters: threshold 0.03, ratio 4 : 1, attack 200 ms,
        release 1 000 ms.  Output: 48 kHz, 24-bit WAV.
        """
        await self._run_ffmpeg(
            "-i",
            voice_path,
            "-i",
            music_path,
            "-filter_complex",
            self._DUCK_FILTER,
            "-ar",
            "48000",
            "-c:a",
            "pcm_s24le",
            output_path,
        )
        await logger.ainfo(
            "music_ducked",
            voice=voice_path,
            music=music_path,
            output=output_path,
        )
        return await self._build_audio_result(output_path)

    async def normalize_loudness(
        self,
        input_path: str,
        output_path: str,
        target_lufs: float = -14.0,
    ) -> AudioResult:
        """Two-pass EBU R128 loudness normalization.

        Pass 1 – measure integrated loudness, true peak, and LRA.
        Pass 2 – apply linear normalization with measured values.

        Targets: −14 LUFS integrated (configurable), −1 dBTP true peak,
        LRA 11.  Output: 48 kHz, 24-bit WAV.
        """
        # Pass 1: measure
        measure_filter = f"loudnorm=I={target_lufs}:TP=-1:LRA=11:print_format=json"
        stderr = await self._run_ffmpeg(
            "-i",
            input_path,
            "-af",
            measure_filter,
            "-f",
            "null",
            os.devnull,
        )
        stats = self._parse_loudnorm_stats(stderr)
        await logger.ainfo(
            "loudnorm_measured",
            input_i=stats["input_i"],
            input_tp=stats["input_tp"],
            input_lra=stats["input_lra"],
        )

        # Pass 2: normalize with linear mode
        apply_filter = (
            f"loudnorm=I={target_lufs}:TP=-1:LRA=11"
            f":measured_I={stats['input_i']}"
            f":measured_TP={stats['input_tp']}"
            f":measured_LRA={stats['input_lra']}"
            f":measured_thresh={stats['input_thresh']}"
            f":offset={stats['target_offset']}"
            ":linear=true"
        )
        await self._run_ffmpeg(
            "-i",
            input_path,
            "-af",
            apply_filter,
            "-ar",
            "48000",
            "-c:a",
            "pcm_s24le",
            output_path,
        )
        await logger.ainfo(
            "loudness_normalized",
            target_lufs=target_lufs,
            output=output_path,
        )
        return await self._build_audio_result(output_path)

    async def mix_final_audio(
        self,
        voice_path: str,
        music_path: str,
        output_path: str,
        sfx_paths: list[SFXCue] | None = None,
    ) -> AudioResult:
        """Full audio post-processing pipeline.

        1. ``process_voiceover``  – EQ the raw narration
        2. ``duck_music_under_voice`` – sidechain-compress music
        3. Overlay SFX cues (stingers + ambient beds) via pydub
        4. ``normalize_loudness`` – two-pass to −14 LUFS

        Returns the final broadcast-ready 48 kHz / 24-bit WAV.
        """
        tmp_dir = tempfile.mkdtemp(prefix="crimemill_audio_")
        try:
            # 1 – EQ voiceover
            eq_voice = os.path.join(tmp_dir, "eq_voice.wav")
            await self.process_voiceover(voice_path, eq_voice)

            # 2 – Duck music under voice
            ducked = os.path.join(tmp_dir, "ducked.wav")
            await self.duck_music_under_voice(eq_voice, music_path, ducked)

            # 3 – Overlay SFX cues
            pre_norm = ducked
            if sfx_paths:
                sfx_mix = os.path.join(tmp_dir, "sfx_mix.wav")
                await asyncio.to_thread(
                    self._overlay_sfx_sync,
                    ducked,
                    sfx_paths,
                    sfx_mix,
                )
                await logger.ainfo(
                    "sfx_overlaid",
                    count=len(sfx_paths),
                    output=sfx_mix,
                )
                pre_norm = sfx_mix

            # 4 – Loudness normalization → final output
            result = await self.normalize_loudness(pre_norm, output_path)

            await logger.ainfo(
                "final_audio_mixed",
                output=output_path,
                duration=result.duration_seconds,
                size_bytes=result.file_size_bytes,
            )
            return result
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

    async def get_audio_info(self, file_path: str) -> AudioInfo:
        """Probe an audio file for format metadata and loudness.

        Uses ``ffprobe`` for stream/format info and the ``loudnorm``
        measurement pass for integrated LUFS and true peak.
        """
        from src.models.audio import AudioInfo

        # --- stream / format metadata via ffprobe ---
        raw = await self._run_ffprobe(
            "-v",
            "quiet",
            "-print_format",
            "json",
            "-show_format",
            "-show_streams",
            file_path,
        )
        probe: dict[str, object] = json.loads(raw)

        streams: list[dict[str, object]] = probe.get("streams", [])  # type: ignore[assignment]
        stream: dict[str, object] = next((s for s in streams if s.get("codec_type") == "audio"), {})
        fmt: dict[str, object] = probe.get("format", {})  # type: ignore[assignment]

        duration = float(str(fmt.get("duration") or stream.get("duration") or 0))
        sample_rate = int(str(stream.get("sample_rate") or 0))
        channels = int(str(stream.get("channels") or 0))
        bit_depth = int(
            str(stream.get("bits_per_raw_sample") or stream.get("bits_per_sample") or 0)
        )
        file_size = int(str(fmt.get("size") or 0)) or os.path.getsize(file_path)

        # --- loudness measurement via loudnorm filter ---
        lufs: float | None = None
        true_peak: float | None = None
        try:
            stderr = await self._run_ffmpeg(
                "-i",
                file_path,
                "-af",
                "loudnorm=I=-14:TP=-1:LRA=11:print_format=json",
                "-f",
                "null",
                os.devnull,
            )
            stats = self._parse_loudnorm_stats(stderr)
            lufs = float(stats["input_i"])
            true_peak = float(stats["input_tp"])
        except (FFmpegError, KeyError, ValueError):
            await logger.awarning("loudness_measure_failed", file=file_path)

        return AudioInfo(
            duration_seconds=duration,
            sample_rate=sample_rate,
            channels=channels,
            bit_depth=bit_depth,
            lufs_integrated=lufs,
            true_peak_dbtp=true_peak,
            file_size_bytes=file_size,
        )

    async def add_silence(
        self,
        input_path: str,
        positions: list[SilenceMarker],
        output_path: str,
    ) -> str:
        """Insert silence gaps at the specified positions.

        Positions are applied in reverse order so that earlier insertions
        do not shift later timestamps.  Returns *output_path*.
        """
        await asyncio.to_thread(
            self._add_silence_sync,
            input_path,
            positions,
            output_path,
        )
        await logger.ainfo(
            "silence_added",
            count=len(positions),
            output=output_path,
        )
        return output_path
