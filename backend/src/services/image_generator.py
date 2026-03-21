from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import httpx

    from src.config import Settings
    from src.models.image import ImageResponse


class ImageGenerator:
    """Generates scene images using fal.ai image generation API.

    Produces high-quality images from the image prompts in each script scene.
    """

    def __init__(self, settings: Settings, http_client: httpx.AsyncClient) -> None:
        self._settings = settings
        self._http = http_client

    async def generate_scene_image(
        self,
        video_id: uuid.UUID,
        scene_number: int,
        prompt: str,
    ) -> ImageResponse:
        """Generate an image for a single scene.

        Sends the image prompt to fal.ai, downloads the result, uploads to R2,
        and records the metadata.
        """
        # Implementation: Batch 1, Prompt P4
        raise NotImplementedError

    async def generate_all_images(self, video_id: uuid.UUID) -> list[ImageResponse]:
        """Generate images for all scenes in a video's script.

        Loads the script, generates images concurrently (with rate limiting),
        and returns all results.
        """
        # Implementation: Batch 1, Prompt P4
        raise NotImplementedError
