from __future__ import annotations

import asyncio
import uuid
from typing import TYPE_CHECKING

import structlog

if TYPE_CHECKING:
    from psycopg_pool import AsyncConnectionPool

    from src.config import Settings

logger = structlog.get_logger()


class Worker:
    """Polls the job queue and processes pipeline stages.

    Runs as a long-lived async task, claiming jobs from the pipeline_jobs
    table using SELECT ... FOR UPDATE SKIP LOCKED for safe concurrency.
    """

    def __init__(
        self,
        settings: Settings,
        db_pool: AsyncConnectionPool,
    ) -> None:
        self._settings = settings
        self._pool = db_pool
        self._running = False

    async def start(self) -> None:
        """Start the worker polling loop."""
        self._running = True
        await logger.ainfo("worker_started")
        while self._running:
            try:
                await self.poll_for_jobs()
            except Exception:
                await logger.aexception("worker_poll_error")
            await asyncio.sleep(self._settings.pipeline_poll_interval_seconds)

    async def stop(self) -> None:
        """Signal the worker to stop after the current iteration."""
        self._running = False
        await logger.ainfo("worker_stopping")

    async def poll_for_jobs(self) -> None:
        """Attempt to claim and process the next available job.

        Uses SKIP LOCKED to avoid contention with other workers.
        """
        # Implementation: Batch 2, Prompt P2
        raise NotImplementedError

    async def process_job(
        self,
        job_id: uuid.UUID,
        video_id: uuid.UUID,
        stage: str,
        payload: dict[str, object],
    ) -> dict[str, object]:
        """Execute the service for a given pipeline stage.

        Dispatches to the appropriate service class based on the stage name,
        tracks costs, and returns the result payload.
        """
        # Implementation: Batch 2, Prompt P2
        raise NotImplementedError

    async def handle_success(
        self,
        job_id: uuid.UUID,
        video_id: uuid.UUID,
        stage: str,
        result: dict[str, object],
    ) -> None:
        """Mark a job as completed and advance the pipeline.

        Updates the job status, records the result, and triggers
        the orchestrator to enqueue dependent stages.
        """
        # Implementation: Batch 2, Prompt P2
        raise NotImplementedError

    async def handle_failure(
        self,
        job_id: uuid.UUID,
        video_id: uuid.UUID,
        stage: str,
        error: Exception,
    ) -> None:
        """Handle a failed job with retry logic.

        Increments retry count, applies exponential backoff for the
        visibility delay, and moves to dead_letter if max retries exceeded.
        """
        # Implementation: Batch 2, Prompt P2
        raise NotImplementedError
