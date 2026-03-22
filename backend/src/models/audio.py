from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel


class AudioMixResponse(BaseModel):
    id: uuid.UUID
    video_id: uuid.UUID
    mixed_audio_url: str
    voice_volume: float
    music_volume: float
    duration_seconds: float
    created_at: datetime

    @classmethod
    def from_row(cls, row: dict[str, object]) -> AudioMixResponse:
        return cls.model_validate(row)


class AudioInfo(BaseModel):
    """Metadata and loudness info from ffprobe."""

    duration_seconds: float = 0.0
    sample_rate: int = 0
    channels: int = 0
    bit_depth: int = 0
    lufs_integrated: float | None = None
    true_peak_dbtp: float | None = None
    file_size_bytes: int = 0


class AudioResult(BaseModel):
    """Result of an audio processing operation."""

    output_path: str
    duration_seconds: float = 0.0
    sample_rate: int = 0
    file_size_bytes: int = 0


class SFXCue(BaseModel):
    """A sound effect cue to overlay on audio."""

    file_path: str
    timestamp_seconds: float
    volume_db: float = 0.0
    cue_type: str = "sfx"
    duration_seconds: float | None = None


class SilenceMarker(BaseModel):
    """A marker indicating where to insert silence."""

    position_seconds: float
    duration_seconds: float = 0.5
