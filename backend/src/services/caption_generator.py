from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import httpx

    from src.config import Settings
    from src.models.caption import CaptionResponse


class CaptionGenerator:
    """Generates word-level captions from voiceover audio using Groq Whisper.

    Transcribes the voiceover audio to get precise word-level timestamps
    for animated caption rendering in the video.
    """

    def __init__(self, settings: Settings, http_client: httpx.AsyncClient) -> None:
        self._settings = settings
        self._http = http_client

    async def generate(self, video_id: uuid.UUID) -> CaptionResponse:
        """Generate word-level captions for the video's voiceover.

        Downloads the concatenated voiceover audio, sends it to Groq's
        Whisper API for transcription with word timestamps, and stores
        the structured caption data.
        """
        # Implementation: Batch 1, Prompt P9
        raise NotImplementedError

    async def generate_srt(self, video_id: uuid.UUID) -> str:
        """Generate an SRT subtitle file from the caption data.

        Loads caption words from the database, groups them into subtitle
        segments, formats as SRT, uploads to R2, and returns the URL.
        """
        # Implementation: Batch 1, Prompt P9
        raise NotImplementedError
