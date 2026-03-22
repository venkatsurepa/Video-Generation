"""Tests for the audio processing pipeline (FFmpeg-based).

Tests EQ chain, loudness normalization, and music ducking.
Requires FFmpeg installed on the system.
"""

from __future__ import annotations

import shutil
import wave
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from src.services.audio_processor import AudioProcessor

if TYPE_CHECKING:
    from src.config import Settings

_HAS_FFMPEG = shutil.which("ffmpeg") is not None

requires_ffmpeg = pytest.mark.skipif(not _HAS_FFMPEG, reason="FFmpeg not installed")


@pytest.fixture
def processor(settings: Settings, mock_http_client: object) -> AudioProcessor:
    return AudioProcessor(settings, mock_http_client)  # type: ignore[arg-type]


@requires_ffmpeg
class TestEQChain:
    async def test_eq_chain_produces_output(
        self,
        processor: AudioProcessor,
        test_audio_path: str,
        tmp_path: Path,
    ) -> None:
        """Process silence through EQ chain and verify output file exists."""
        output = str(tmp_path / "processed.wav")
        result = await processor.process_voiceover(test_audio_path, output)

        assert Path(result.output_path).exists()
        assert result.duration_seconds > 0
        assert result.file_size_bytes > 0

    async def test_eq_preserves_duration(
        self,
        processor: AudioProcessor,
        test_audio_with_tone: str,
        tmp_path: Path,
    ) -> None:
        """EQ processing should preserve audio duration (within 0.1s tolerance)."""
        # Get original duration
        with wave.open(test_audio_with_tone) as wf:
            orig_duration = wf.getnframes() / wf.getframerate()

        output = str(tmp_path / "eq_output.wav")
        result = await processor.process_voiceover(test_audio_with_tone, output)

        assert abs(result.duration_seconds - orig_duration) < 0.1


@requires_ffmpeg
class TestLoudnessNormalization:
    async def test_loudness_normalization_produces_output(
        self,
        processor: AudioProcessor,
        test_audio_with_tone: str,
        tmp_path: Path,
    ) -> None:
        """Loudness normalization should produce a valid output file."""
        output = str(tmp_path / "normalized.wav")
        result = await processor.normalize_loudness(test_audio_with_tone, output, target_lufs=-14.0)

        assert Path(result.output_path).exists()
        assert result.file_size_bytes > 0

    async def test_loudness_normalization_target(
        self,
        processor: AudioProcessor,
        test_audio_with_tone: str,
        tmp_path: Path,
    ) -> None:
        """Output should be within 2 LUFS of the -14 target."""
        output = str(tmp_path / "normalized.wav")
        await processor.normalize_loudness(test_audio_with_tone, output, target_lufs=-14.0)

        info = await processor.get_audio_info(output)
        if info.lufs_integrated is not None:
            assert abs(info.lufs_integrated - (-14.0)) < 2.0, (
                f"LUFS {info.lufs_integrated} not within 2 of target -14"
            )


@requires_ffmpeg
class TestAudioInfo:
    async def test_get_audio_info_returns_metadata(
        self,
        processor: AudioProcessor,
        test_audio_path: str,
    ) -> None:
        """get_audio_info should return valid metadata for a WAV file."""
        info = await processor.get_audio_info(test_audio_path)

        assert info.duration_seconds > 0
        assert info.sample_rate == 48000
        assert info.channels >= 1
        assert info.file_size_bytes > 0

    async def test_get_audio_info_tone_file(
        self,
        processor: AudioProcessor,
        test_audio_with_tone: str,
    ) -> None:
        """Audio info for a 2-second tone should report ~2s duration."""
        info = await processor.get_audio_info(test_audio_with_tone)
        assert abs(info.duration_seconds - 2.0) < 0.1


@requires_ffmpeg
class TestDucking:
    async def test_ducking_produces_output(
        self,
        processor: AudioProcessor,
        test_audio_with_tone: str,
        test_audio_path: str,
        tmp_path: Path,
    ) -> None:
        """duck_music_under_voice should produce a valid output file."""
        output = str(tmp_path / "ducked.wav")
        result = await processor.duck_music_under_voice(
            voice_path=test_audio_with_tone,
            music_path=test_audio_path,
            output_path=output,
        )

        assert Path(result.output_path).exists()
        assert result.duration_seconds > 0


@requires_ffmpeg
class TestFinalMix:
    async def test_mix_final_audio_produces_output(
        self,
        processor: AudioProcessor,
        test_audio_with_tone: str,
        test_audio_path: str,
        tmp_path: Path,
    ) -> None:
        """mix_final_audio should combine voice and music into a single file."""
        output = str(tmp_path / "final_mix.wav")
        result = await processor.mix_final_audio(
            voice_path=test_audio_with_tone,
            music_path=test_audio_path,
            output_path=output,
        )

        assert Path(result.output_path).exists()
        assert result.duration_seconds > 0
        assert result.file_size_bytes > 0
