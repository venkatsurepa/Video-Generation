from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

import structlog

from src.pipeline.stages import PIPELINE_STAGES

if TYPE_CHECKING:
    from psycopg import AsyncConnection

logger = structlog.get_logger()


class Orchestrator:
    """Manages pipeline execution by tracking stage dependencies and dispatching ready jobs.

    The orchestrator examines which stages have completed for a given video
    and enqueues any stages whose dependencies are fully satisfied.
    """

    def __init__(self, db: AsyncConnection[dict[str, object]]) -> None:
        self._db = db

    async def start_pipeline(self, video_id: uuid.UUID) -> list[str]:
        """Kick off a new pipeline run by enqueuing the initial stage(s).

        Creates pipeline_jobs rows for all stages with no dependencies
        (i.e., script_generation). Returns the list of enqueued stage names.
        """
        # Implementation: Batch 2, Prompt P1
        raise NotImplementedError

    async def advance_pipeline(
        self,
        video_id: uuid.UUID,
        completed_stage: str,
    ) -> list[str]:
        """Advance the pipeline after a stage completes.

        Checks all stages that depend on the completed stage. For each one,
        if all its dependencies are now satisfied, enqueue it. Returns the
        list of newly enqueued stage names.
        """
        # Implementation: Batch 2, Prompt P1
        raise NotImplementedError

    async def get_ready_stages(self, video_id: uuid.UUID) -> list[str]:
        """Determine which stages are ready to run.

        Queries completed stages for this video and returns any stages
        from PIPELINE_STAGES whose dependencies are all satisfied and
        that haven't been enqueued yet.
        """
        # Implementation: Batch 2, Prompt P1
        raise NotImplementedError

    async def cancel_pipeline(self, video_id: uuid.UUID) -> int:
        """Cancel all pending/running jobs for a video.

        Sets status to 'cancelled' for all non-completed jobs.
        Returns the number of jobs cancelled.
        """
        # Implementation: Batch 2, Prompt P1
        raise NotImplementedError

    @staticmethod
    def get_dependents(stage: str) -> list[str]:
        """Return all stages that directly depend on the given stage."""
        return [
            name
            for name, config in PIPELINE_STAGES.items()
            if stage in config["depends_on"]
        ]
