from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import httpx

    from src.config import Settings
    from src.models.assembly import AssemblyResponse


class VideoAssembler:
    """Assembles the final video using Remotion.

    Prepares input props from all generated assets and triggers
    a Remotion render (local or Lambda) to produce the final MP4.
    """

    def __init__(self, settings: Settings, http_client: httpx.AsyncClient) -> None:
        self._settings = settings
        self._http = http_client

    async def assemble(self, video_id: uuid.UUID) -> AssemblyResponse:
        """Assemble all assets into a final video.

        Gathers processed images, mixed audio, and caption data.
        Builds Remotion input props and triggers a render.
        Uploads the final MP4 to R2 and records metadata.
        """
        # Implementation: Batch 1, Prompt P7
        raise NotImplementedError

    async def prepare_remotion_props(self, video_id: uuid.UUID) -> dict[str, object]:
        """Build the Remotion composition input props from database records.

        Loads all assets (images, audio, captions, script timing) and
        constructs the VideoProps structure expected by the Remotion composition.
        """
        # Implementation: Batch 1, Prompt P7
        raise NotImplementedError
