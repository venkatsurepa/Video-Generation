from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import httpx

    from src.config import Settings
    from src.models.script import ScriptResponse


class ScriptGenerator:
    """Generates crime documentary scripts using Claude.

    Takes a topic and produces a multi-scene narration script with
    image prompts, timing, hook, and outro.
    """

    def __init__(self, settings: Settings, http_client: httpx.AsyncClient) -> None:
        self._settings = settings
        self._http = http_client

    async def generate(self, video_id: uuid.UUID, topic: str) -> ScriptResponse:
        """Generate a full documentary script for the given topic.

        Uses Claude to produce a structured script with scenes, narration text,
        image generation prompts, and timing information.
        """
        # Implementation: Batch 1, Prompt P2
        raise NotImplementedError

    async def refine(self, video_id: uuid.UUID, feedback: str) -> ScriptResponse:
        """Refine an existing script based on editorial feedback.

        Loads the current script from the database, sends it back to Claude
        with the feedback, and returns the updated version.
        """
        # Implementation: Batch 1, Prompt P2
        raise NotImplementedError
