from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import httpx

    from src.config import Settings


class YouTubeUploader:
    """Uploads finished videos to YouTube via the Data API v3.

    Handles OAuth token refresh, video upload with resumable uploads,
    thumbnail setting, and metadata (title, description, tags).
    """

    def __init__(self, settings: Settings, http_client: httpx.AsyncClient) -> None:
        self._settings = settings
        self._http = http_client

    async def upload(self, video_id: uuid.UUID) -> str:
        """Upload the assembled video to YouTube.

        Downloads the final MP4 and thumbnail from R2, initiates a
        resumable upload to YouTube, sets the thumbnail, and returns
        the YouTube video ID.
        """
        # Implementation: Batch 1, Prompt P10
        raise NotImplementedError

    async def set_thumbnail(self, youtube_video_id: str, thumbnail_url: str) -> None:
        """Set the custom thumbnail for an uploaded YouTube video.

        Downloads the thumbnail from R2 and uploads it via the
        YouTube thumbnails.set API endpoint.
        """
        # Implementation: Batch 1, Prompt P10
        raise NotImplementedError

    async def update_metadata(
        self,
        youtube_video_id: str,
        title: str,
        description: str,
        tags: list[str],
    ) -> None:
        """Update the metadata of an already-uploaded YouTube video."""
        # Implementation: Batch 1, Prompt P10
        raise NotImplementedError
