"""Tests for the caption generator — SRT formatting and Remotion word data.

Tests the deterministic formatting logic (no API calls needed).
Integration tests with Groq Whisper require GROQ_API_KEY.
"""

from __future__ import annotations

import re

from src.models.caption import GroqTranscriptResponse, WordTimestamp
from src.services.caption_generator import (
    MAX_WORDS_PER_BLOCK,
    MIN_WORDS_PER_BLOCK,
    CaptionGenerator,
)

# ---------------------------------------------------------------------------
# Test data
# ---------------------------------------------------------------------------


def _make_words(count: int = 30, gap: float = 0.3) -> list[WordTimestamp]:
    """Generate evenly-spaced WordTimestamp objects for testing."""
    words = []
    word_texts = [
        "The",
        "detective",
        "arrived",
        "at",
        "the",
        "scene",
        "and",
        "found",
        "evidence",
        "that",
        "changed",
        "everything",
        "about",
        "this",
        "cold",
        "case",
        "from",
        "nineteen",
        "ninety",
        "five",
        "when",
        "the",
        "victim",
        "was",
        "last",
        "seen",
        "near",
        "the",
        "old",
        "bridge",
    ]
    t = 0.0
    for i in range(count):
        word = word_texts[i % len(word_texts)]
        duration = 0.2
        words.append(WordTimestamp(word=word, start=t, end=t + duration))
        t += duration + gap
    return words


# ---------------------------------------------------------------------------
# SRT format tests
# ---------------------------------------------------------------------------


class TestSRTFormat:
    def test_srt_format_valid(self) -> None:
        """SRT output should have correctly numbered blocks and timestamps."""
        words = _make_words(20)
        srt = CaptionGenerator.format_srt(words)

        # Should have numbered blocks
        blocks = [b.strip() for b in srt.strip().split("\n\n") if b.strip()]
        assert len(blocks) >= 2

        for i, block in enumerate(blocks, 1):
            lines = block.split("\n")
            assert len(lines) == 3, f"Block {i} should have 3 lines"
            # First line: block number
            assert lines[0] == str(i)
            # Second line: timestamp range
            assert "-->" in lines[1]
            # Timestamp format: HH:MM:SS,mmm
            ts_pattern = r"\d{2}:\d{2}:\d{2},\d{3}"
            assert re.match(f"{ts_pattern} --> {ts_pattern}", lines[1])
            # Third line: non-empty text
            assert len(lines[2].strip()) > 0

    def test_words_per_block_5_to_7(self) -> None:
        """SRT blocks should contain 5-7 words each (except possibly the last)."""
        words = _make_words(30)
        srt = CaptionGenerator.format_srt(words)

        blocks = [b.strip() for b in srt.strip().split("\n\n") if b.strip()]
        for i, block in enumerate(blocks):
            text_line = block.split("\n")[2]
            word_count = len(text_line.split())
            # Last block may have fewer words
            if i < len(blocks) - 1:
                assert MIN_WORDS_PER_BLOCK <= word_count <= MAX_WORDS_PER_BLOCK, (
                    f"Block {i + 1} has {word_count} words, expected {MIN_WORDS_PER_BLOCK}-{MAX_WORDS_PER_BLOCK}"
                )

    def test_srt_timestamps_are_sequential(self) -> None:
        """SRT timestamps should be monotonically increasing."""
        words = _make_words(20)
        srt = CaptionGenerator.format_srt(words)

        blocks = [b.strip() for b in srt.strip().split("\n\n") if b.strip()]
        prev_end = -1.0

        for block in blocks:
            ts_line = block.split("\n")[1]
            start_str, end_str = ts_line.split(" --> ")
            start = _parse_srt_time(start_str)
            end = _parse_srt_time(end_str)

            assert start >= prev_end, "Block start should be >= previous block end"
            assert end > start, "Block end should be > block start"
            prev_end = end

    def test_srt_empty_words_returns_empty(self) -> None:
        """Empty word list should produce empty SRT."""
        assert CaptionGenerator.format_srt([]) == ""

    def test_srt_natural_pause_break(self) -> None:
        """SRT should break at natural pauses (>300ms gap)."""
        # Create words with a big pause after word 5
        words = []
        t = 0.0
        for i in range(12):
            words.append(WordTimestamp(word=f"word{i}", start=t, end=t + 0.2))
            if i == 4:
                t += 0.2 + 0.5  # 500ms gap (pause)
            else:
                t += 0.2 + 0.1  # 100ms gap (normal)

        srt = CaptionGenerator.format_srt(words)
        blocks = [b.strip() for b in srt.strip().split("\n\n") if b.strip()]

        # First block should break at the pause point
        first_block_text = blocks[0].split("\n")[2]
        first_word_count = len(first_block_text.split())
        assert first_word_count == 5, "Should break at the natural pause after word 5"


# ---------------------------------------------------------------------------
# Remotion caption tests
# ---------------------------------------------------------------------------


class TestRemotionCaptions:
    def test_remotion_caption_frames_sequential(self) -> None:
        """Frame numbers should be monotonically increasing."""
        words = _make_words(15)
        captions = CaptionGenerator.prepare_remotion_captions(words, fps=30)

        prev_start = -1
        for cw in captions:
            assert cw.start_frame >= prev_start, "start_frame should be non-decreasing"
            assert cw.end_frame > cw.start_frame, "end_frame must be > start_frame"
            prev_start = cw.start_frame

    def test_remotion_caption_count_matches_words(self) -> None:
        """Each word should produce exactly one CaptionWord."""
        words = _make_words(10)
        captions = CaptionGenerator.prepare_remotion_captions(words, fps=30)
        assert len(captions) == len(words)

    def test_remotion_caption_fps_affects_frames(self) -> None:
        """Higher FPS should produce higher frame numbers."""
        words = [WordTimestamp(word="test", start=1.0, end=2.0)]
        captions_30 = CaptionGenerator.prepare_remotion_captions(words, fps=30)
        captions_60 = CaptionGenerator.prepare_remotion_captions(words, fps=60)

        assert captions_60[0].start_frame == captions_30[0].start_frame * 2
        assert captions_60[0].end_frame == captions_30[0].end_frame * 2

    def test_remotion_caption_text_stripped(self) -> None:
        """Word text should be stripped of whitespace."""
        words = [WordTimestamp(word="  hello  ", start=0.0, end=0.5)]
        captions = CaptionGenerator.prepare_remotion_captions(words, fps=30)
        assert captions[0].text == "hello"


# ---------------------------------------------------------------------------
# Merge transcription tests
# ---------------------------------------------------------------------------


class TestMergeTranscriptions:
    def test_merge_applies_offsets(self) -> None:
        """Merging chunks should add time offsets to each chunk's words."""
        chunk1 = GroqTranscriptResponse(
            text="hello world",
            words=[
                WordTimestamp(word="hello", start=0.0, end=0.5),
                WordTimestamp(word="world", start=0.6, end=1.0),
            ],
            language="en",
            duration=1.0,
        )
        chunk2 = GroqTranscriptResponse(
            text="goodbye",
            words=[
                WordTimestamp(word="goodbye", start=0.0, end=0.5),
            ],
            language="en",
            duration=0.5,
        )

        merged = CaptionGenerator.merge_transcriptions([chunk1, chunk2], [0.0, 1.0])

        assert len(merged) == 3
        assert merged[0].start == 0.0
        assert merged[0].word == "hello"
        assert merged[2].start == 1.0  # 0.0 + 1.0 offset
        assert merged[2].word == "goodbye"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _parse_srt_time(ts: str) -> float:
    """Parse SRT timestamp (HH:MM:SS,mmm) to seconds."""
    parts = ts.replace(",", ".").split(":")
    return float(parts[0]) * 3600 + float(parts[1]) * 60 + float(parts[2])
