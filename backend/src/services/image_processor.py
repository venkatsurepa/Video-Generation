from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import httpx

    from src.config import Settings


class ImageProcessor:
    """Post-processes generated images for video composition.

    Applies Ken Burns effect metadata, resizes/crops to target resolution,
    and prepares image sequences for Remotion rendering.
    """

    def __init__(self, settings: Settings, http_client: httpx.AsyncClient) -> None:
        self._settings = settings
        self._http = http_client

    async def process_scene_image(
        self,
        video_id: uuid.UUID,
        scene_number: int,
        image_url: str,
        target_width: int = 1920,
        target_height: int = 1080,
    ) -> str:
        """Process a single scene image for video use.

        Downloads the image, resizes/crops to the target resolution,
        uploads the processed version to R2, and returns the new URL.
        """
        # Implementation: Batch 1, Prompt P5
        raise NotImplementedError

    async def process_all_images(self, video_id: uuid.UUID) -> list[str]:
        """Process all scene images for a video.

        Loads image records from the database, processes each one,
        and returns the list of processed image URLs.
        """
        # Implementation: Batch 1, Prompt P5
        raise NotImplementedError
