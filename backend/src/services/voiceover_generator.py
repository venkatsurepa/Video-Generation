from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import httpx

    from src.config import Settings
    from src.models.voiceover import VoiceoverResponse


class VoiceoverGenerator:
    """Generates narration audio using Fish Audio TTS API.

    Converts script narration text into spoken audio files, one per scene.
    """

    def __init__(self, settings: Settings, http_client: httpx.AsyncClient) -> None:
        self._settings = settings
        self._http = http_client

    async def generate_scene(
        self,
        video_id: uuid.UUID,
        scene_number: int,
        narration_text: str,
    ) -> VoiceoverResponse:
        """Generate voiceover audio for a single scene.

        Sends narration text to Fish Audio API, downloads the resulting audio,
        uploads to R2, and records the metadata.
        """
        # Implementation: Batch 1, Prompt P3
        raise NotImplementedError

    async def generate_all_scenes(self, video_id: uuid.UUID) -> list[VoiceoverResponse]:
        """Generate voiceover for all scenes in a video's script.

        Loads the script from the database, generates audio for each scene
        concurrently, and returns all results.
        """
        # Implementation: Batch 1, Prompt P3
        raise NotImplementedError
