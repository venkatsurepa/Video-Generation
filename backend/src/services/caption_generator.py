from __future__ import annotations

import asyncio
import tempfile
import time
from decimal import Decimal
from functools import partial
from pathlib import Path
from typing import TYPE_CHECKING

import structlog
from pydub import AudioSegment
from pydub.silence import detect_silence

from src.models.caption import (
    CaptionResult,
    CaptionWord,
    GroqTranscriptResponse,
    WordTimestamp,
)
from src.utils.retry import async_retry

if TYPE_CHECKING:
    import httpx

    from src.config import Settings

logger = structlog.get_logger()

GROQ_TRANSCRIPTION_URL = "https://api.groq.com/openai/v1/audio/transcriptions"
GROQ_MODEL = "whisper-large-v3-turbo"

# $0.00067 per minute of audio
COST_PER_MINUTE_USD = Decimal("0.00067")

# Groq file size limit
MAX_FILE_SIZE_MB = 25
MAX_FILE_SIZE_BYTES = MAX_FILE_SIZE_MB * 1024 * 1024

# SRT block sizing — phrase-based, not sentence-based
DEFAULT_WORDS_PER_BLOCK = 6
MIN_WORDS_PER_BLOCK = 5
MAX_WORDS_PER_BLOCK = 7

# Pause threshold for natural SRT breaks (seconds)
PAUSE_THRESHOLD_SECONDS = 0.3


class CaptionGenerator:
    """Generates captions using Groq's hosted Whisper API (dual strategy).

    Produces:
      1. SRT file — uploaded to YouTube for SEO (15x more searchable text)
      2. Word-level CaptionWord list — feeds Remotion for burned-in captions

    Cost: $0.00067/minute via whisper-large-v3-turbo (294x real-time speed).
    """

    def __init__(self, settings: Settings, http_client: httpx.AsyncClient) -> None:
        self._settings = settings
        self._http = http_client
        self._tmp_dir = Path(tempfile.gettempdir()) / "crimemill" / "captions"
        self._tmp_dir.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def generate_srt(
        self,
        audio_path: str,
        language: str = "en",
        fps: int = 30,
    ) -> CaptionResult:
        """Full caption pipeline: transcribe → SRT + Remotion word data.

        Handles audio chunking for files >25MB, merges results, and produces
        both SRT content and frame-based CaptionWord list.
        """
        start = time.monotonic()

        chunk_paths = await self.split_audio_if_needed(audio_path)

        if len(chunk_paths) == 1:
            transcript = await self.transcribe_with_groq(chunk_paths[0], language)
            words = transcript.words
            duration = transcript.duration
        else:
            # Transcribe chunks concurrently, merge with time offsets
            chunk_offsets = await self._compute_chunk_offsets(chunk_paths)
            transcripts = await asyncio.gather(
                *[self.transcribe_with_groq(p, language) for p in chunk_paths]
            )
            words = self.merge_transcriptions(list(transcripts), chunk_offsets)
            duration = chunk_offsets[-1] + transcripts[-1].duration

        srt_content = self.format_srt(words)
        caption_words = self.prepare_remotion_captions(words, fps)

        # Write SRT to temp file
        srt_path = self._tmp_dir / f"{Path(audio_path).stem}.srt"
        srt_path.write_text(srt_content, encoding="utf-8")

        # Cost: $0.00067/minute
        duration_minutes = Decimal(str(duration)) / Decimal("60")
        cost_usd = (duration_minutes * COST_PER_MINUTE_USD).quantize(Decimal("0.00001"))

        elapsed = time.monotonic() - start

        await logger.ainfo(
            "captions_generated",
            total_words=len(words),
            srt_blocks=srt_content.count("\n\n") + 1,
            duration_seconds=round(duration, 2),
            cost_usd=str(cost_usd),
            elapsed_seconds=round(elapsed, 2),
            chunks=len(chunk_paths),
        )

        # Clean up temp chunks (but not original audio or SRT)
        if len(chunk_paths) > 1:
            for p in chunk_paths:
                Path(p).unlink(missing_ok=True)

        return CaptionResult(
            srt_content=srt_content,
            srt_file_path=str(srt_path),
            caption_words=caption_words,
            word_timestamps=words,
            total_words=len(words),
            duration_seconds=duration,
            cost_usd=cost_usd,
            transcription_time_seconds=round(elapsed, 3),
            needs_human_review=True,
        )

    # ------------------------------------------------------------------
    # Groq Whisper API
    # ------------------------------------------------------------------

    @async_retry(max_attempts=3, base_delay=2.0)
    async def transcribe_with_groq(
        self,
        audio_path: str,
        language: str = "en",
    ) -> GroqTranscriptResponse:
        """Send audio to Groq Whisper API, return word-level timestamps.

        POST https://api.groq.com/openai/v1/audio/transcriptions
        multipart/form-data with verbose_json + word-level granularity.
        """
        audio_bytes = Path(audio_path).read_bytes()
        filename = Path(audio_path).name

        # Determine MIME type from extension
        ext = Path(audio_path).suffix.lower()
        mime_types = {
            ".wav": "audio/wav",
            ".mp3": "audio/mpeg",
            ".m4a": "audio/mp4",
            ".ogg": "audio/ogg",
            ".flac": "audio/flac",
            ".webm": "audio/webm",
        }
        content_type = mime_types.get(ext, "audio/wav")

        await logger.ainfo(
            "groq_transcribe_start",
            audio_path=audio_path,
            size_mb=round(len(audio_bytes) / (1024 * 1024), 2),
            language=language,
        )

        resp = await self._http.post(
            GROQ_TRANSCRIPTION_URL,
            headers={"Authorization": f"Bearer {self._settings.groq.api_key}"},
            files={"file": (filename, audio_bytes, content_type)},
            data={
                "model": GROQ_MODEL,
                "response_format": "verbose_json",
                "timestamp_granularities[]": "word",
                "language": language,
            },
            timeout=120.0,
        )
        resp.raise_for_status()
        data = resp.json()

        words = [
            WordTimestamp(word=w["word"], start=w["start"], end=w["end"])
            for w in data.get("words", [])
        ]

        await logger.ainfo(
            "groq_transcribe_complete",
            words=len(words),
            duration=data.get("duration", 0),
            language=data.get("language", language),
        )

        return GroqTranscriptResponse(
            text=data.get("text", ""),
            words=words,
            language=data.get("language", language),
            duration=data.get("duration", 0.0),
        )

    # ------------------------------------------------------------------
    # SRT formatting
    # ------------------------------------------------------------------

    @staticmethod
    def format_srt(
        words: list[WordTimestamp],
        words_per_block: int = DEFAULT_WORDS_PER_BLOCK,
    ) -> str:
        """Convert word timestamps to SRT format.

        Groups words into blocks of 5-7 words, breaking at natural pause
        points (>300ms gap) when possible for phrase-based segmentation.
        """
        if not words:
            return ""

        blocks: list[tuple[float, float, str]] = []
        current_words: list[WordTimestamp] = []

        for i, word in enumerate(words):
            current_words.append(word)

            at_max = len(current_words) >= MAX_WORDS_PER_BLOCK
            at_min = len(current_words) >= MIN_WORDS_PER_BLOCK
            is_last = i == len(words) - 1

            # Check for natural pause after this word
            has_pause = False
            if not is_last:
                gap = words[i + 1].start - word.end
                has_pause = gap >= PAUSE_THRESHOLD_SECONDS

            should_break = is_last or at_max or (at_min and has_pause)

            if should_break and current_words:
                block_start = current_words[0].start
                block_end = current_words[-1].end
                block_text = " ".join(w.word.strip() for w in current_words)
                blocks.append((block_start, block_end, block_text))
                current_words = []

        # Build SRT string
        lines: list[str] = []
        for idx, (start, end, text) in enumerate(blocks, 1):
            lines.append(str(idx))
            lines.append(f"{_format_srt_time(start)} --> {_format_srt_time(end)}")
            lines.append(text)
            lines.append("")

        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Remotion caption preparation
    # ------------------------------------------------------------------

    @staticmethod
    def prepare_remotion_captions(
        words: list[WordTimestamp],
        fps: int = 30,
    ) -> list[CaptionWord]:
        """Convert word timestamps to Remotion frame-based CaptionWord list.

        Each word gets start_frame and end_frame computed from its timestamp.
        The Remotion Captions component uses these to show/highlight words
        frame-by-frame during playback.
        """
        return [
            CaptionWord(
                text=w.word.strip(),
                start_frame=int(w.start * fps),
                end_frame=int(w.end * fps),
            )
            for w in words
        ]

    # ------------------------------------------------------------------
    # Audio chunking (Groq 25MB limit)
    # ------------------------------------------------------------------

    async def split_audio_if_needed(
        self,
        audio_path: str,
        max_size_mb: int = MAX_FILE_SIZE_MB,
    ) -> list[str]:
        """Split audio into chunks if it exceeds Groq's 25MB file size limit.

        For a typical 15-20 min narration WAV at 48kHz this is ~100-150MB,
        requiring 4-6 chunks. Splits at silence points to avoid cutting
        mid-word.
        """
        file_size = Path(audio_path).stat().st_size
        max_bytes = max_size_mb * 1024 * 1024

        if file_size <= max_bytes:
            return [audio_path]

        await logger.ainfo(
            "audio_split_needed",
            file_size_mb=round(file_size / (1024 * 1024), 2),
            max_size_mb=max_size_mb,
        )

        # CPU-bound pydub work — run in thread pool
        loop = asyncio.get_running_loop()
        chunk_paths = await loop.run_in_executor(
            None,
            partial(self._split_at_silence, audio_path, max_bytes),
        )

        await logger.ainfo("audio_split_complete", chunks=len(chunk_paths))
        return chunk_paths

    def _split_at_silence(self, audio_path: str, max_bytes: int) -> list[str]:
        """Synchronous audio splitting at silence points via pydub."""
        audio = AudioSegment.from_file(audio_path)
        total_ms = len(audio)

        # Estimate how many chunks we need from file size ratio
        file_size = Path(audio_path).stat().st_size
        num_chunks = max(2, -(-file_size // max_bytes))  # ceil division
        target_chunk_ms = total_ms // num_chunks

        # Find silence points to use as split candidates
        silences = detect_silence(audio, min_silence_len=300, silence_thresh=-40)

        # Build split points near target boundaries
        split_points: list[int] = [0]
        for i in range(1, num_chunks):
            target = i * target_chunk_ms
            # Find the nearest silence point to the target
            best_silence = _find_nearest_silence(silences, target)
            if best_silence is not None:
                split_points.append(best_silence)
            else:
                split_points.append(target)
        split_points.append(total_ms)

        # Deduplicate and sort
        split_points = sorted(set(split_points))

        # Export chunks
        chunk_paths: list[str] = []
        for i in range(len(split_points) - 1):
            chunk = audio[split_points[i] : split_points[i + 1]]
            chunk_path = str(self._tmp_dir / f"chunk_{i:03d}.wav")
            chunk.export(chunk_path, format="wav")
            chunk_paths.append(chunk_path)

        return chunk_paths

    async def _compute_chunk_offsets(self, chunk_paths: list[str]) -> list[float]:
        """Compute the time offset (in seconds) for each audio chunk."""
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, partial(_chunk_offsets_sync, chunk_paths))

    # ------------------------------------------------------------------
    # Multi-chunk merging
    # ------------------------------------------------------------------

    @staticmethod
    def merge_transcriptions(
        chunks: list[GroqTranscriptResponse],
        chunk_offsets: list[float],
    ) -> list[WordTimestamp]:
        """Merge multiple chunk transcriptions into a single timeline.

        Adds each chunk's start offset to every word timestamp so the
        merged result has absolute times from the beginning of the full audio.
        """
        merged: list[WordTimestamp] = []
        for transcript, offset in zip(chunks, chunk_offsets, strict=True):
            for w in transcript.words:
                merged.append(
                    WordTimestamp(
                        word=w.word,
                        start=round(w.start + offset, 3),
                        end=round(w.end + offset, 3),
                    )
                )
        return merged


# ---------- Module-level helpers ----------


def _format_srt_time(seconds: float) -> str:
    """Format seconds as SRT timestamp: HH:MM:SS,mmm"""
    total_ms = int(round(seconds * 1000))
    hours, remainder = divmod(total_ms, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    secs, ms = divmod(remainder, 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{ms:03d}"


def _find_nearest_silence(
    silences: list[list[int]],
    target_ms: int,
) -> int | None:
    """Find the midpoint of the silence segment nearest to target_ms.

    Returns None if no silences exist.
    """
    if not silences:
        return None
    best: int | None = None
    best_dist = float("inf")
    for start, end in silences:
        mid = (start + end) // 2
        dist = abs(mid - target_ms)
        if dist < best_dist:
            best_dist = dist
            best = mid
    return best


def _chunk_offsets_sync(chunk_paths: list[str]) -> list[float]:
    """Compute cumulative time offsets for a list of audio chunk files."""
    offsets: list[float] = []
    cumulative = 0.0
    for path in chunk_paths:
        offsets.append(cumulative)
        audio = AudioSegment.from_file(path)
        cumulative += len(audio) / 1000.0  # pydub lengths are in ms
    return offsets
