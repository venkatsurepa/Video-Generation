"""Pipeline orchestrator — manages stage dependencies and dispatches ready jobs.

The orchestrator examines which stages have completed for a given video and
enqueues any stages whose dependencies are fully satisfied.  It also maps
stage completions to video-level status transitions.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

import structlog

from src.db.queries import (
    CANCEL_PIPELINE_JOBS,
    CREATE_JOB,
    GET_COMPLETED_STAGES,
    GET_ENQUEUED_STAGES,
    GET_PIPELINE_JOBS,
    GET_VIDEO_STATUS,
    RETRY_FAILED_JOBS,
    UPDATE_VIDEO_STATUS,
)
from src.models.pipeline import PipelineJobResponse, PipelineStatusResponse
from src.pipeline.stages import PIPELINE_STAGES

if TYPE_CHECKING:
    import uuid

    from psycopg import AsyncConnection

logger = structlog.get_logger()

# Stage → video status mapping for progress tracking
_STAGE_TO_VIDEO_STATUS: dict[str, str] = {
    "script_generation": "script_generated",
    "youtube_upload": "published",
    "video_assembly": "assembled",
}

# All media stages that must complete before "media_complete"
_MEDIA_STAGES: frozenset[str] = frozenset(
    {
        "audio_processing",
        "image_processing",
        "caption_generation",
        "thumbnail_generation",
    }
)


class Orchestrator:
    """Manages pipeline execution by tracking stage dependencies and dispatching ready jobs.

    The orchestrator examines which stages have completed for a given video
    and enqueues any stages whose dependencies are fully satisfied.
    """

    def __init__(self, db: AsyncConnection[dict[str, object]]) -> None:
        self._db = db

    async def start_pipeline(
        self,
        video_id: uuid.UUID,
        payload: dict[str, Any] | None = None,
    ) -> list[str]:
        """Kick off a new pipeline run by enqueuing the initial stage(s).

        Creates pipeline_jobs rows for all stages with no dependencies
        (i.e., script_generation). Returns the list of enqueued stage names.
        """
        log = logger.bind(video_id=str(video_id))
        await log.ainfo("pipeline_starting")

        # Set video status to media_generating
        await self._db.execute(
            UPDATE_VIDEO_STATUS,
            {"video_id": video_id, "status": "media_generating"},
        )

        # Enqueue root stages (no dependencies)
        enqueued: list[str] = []
        for stage_name, config in PIPELINE_STAGES.items():
            if not config["depends_on"]:
                await self._create_job(video_id, stage_name, payload or {}, priority=10)
                enqueued.append(stage_name)

        await log.ainfo("pipeline_started", enqueued_stages=enqueued)
        return enqueued

    async def advance_pipeline(
        self,
        video_id: uuid.UUID,
        completed_stage: str,
        completed_result: dict[str, Any] | None = None,
    ) -> list[str]:
        """Advance the pipeline after a stage completes.

        Checks all stages that depend on the completed stage. For each one,
        if all its dependencies are now satisfied and it hasn't already been
        enqueued, create a new job. Returns the list of newly enqueued stage names.
        """
        log = logger.bind(video_id=str(video_id), completed_stage=completed_stage)

        # Update video status based on what just completed
        await self._update_video_status(video_id, completed_stage)

        # Get completed and already-enqueued stages
        completed_stages = await self._get_completed_stages(video_id)
        enqueued_stages = await self._get_enqueued_stages(video_id)

        # Gather results from all completed jobs to build payloads
        completed_results = await self._get_completed_results(video_id)

        # Find dependents of the completed stage and check readiness
        dependents = self.get_dependents(completed_stage)
        newly_enqueued: list[str] = []

        for dep_stage in dependents:
            if dep_stage in enqueued_stages:
                continue

            deps = PIPELINE_STAGES[dep_stage]["depends_on"]
            if all(d in completed_stages for d in deps):
                # Build payload from upstream results
                payload = self._build_downstream_payload(dep_stage, completed_results)
                await self._create_job(video_id, dep_stage, payload)
                newly_enqueued.append(dep_stage)

        if newly_enqueued:
            await log.ainfo("stages_enqueued", stages=newly_enqueued)

        # Core pipeline complete — post-upload stages still pending
        if completed_stage == "youtube_upload":
            await log.ainfo("core_pipeline_complete")

        return newly_enqueued

    async def get_pipeline_status(self, video_id: uuid.UUID) -> PipelineStatusResponse:
        """Return full pipeline status including all jobs for a video."""
        cur = await self._db.execute(GET_VIDEO_STATUS, {"video_id": video_id})
        video_row = await cur.fetchone()
        video_status = str(video_row["status"]) if video_row else "unknown"

        cur = await self._db.execute(GET_PIPELINE_JOBS, {"video_id": video_id})
        rows = await cur.fetchall()
        jobs = [PipelineJobResponse.from_row(r) for r in rows]

        return PipelineStatusResponse(
            video_id=video_id,
            video_status=video_status,
            jobs=jobs,
        )

    async def cancel_pipeline(self, video_id: uuid.UUID) -> int:
        """Cancel all pending/in_progress jobs for a video.

        Returns the number of jobs cancelled.
        """
        log = logger.bind(video_id=str(video_id))

        cur = await self._db.execute(CANCEL_PIPELINE_JOBS, {"video_id": video_id})
        rows = await cur.fetchall()
        count = len(rows)

        await self._db.execute(
            UPDATE_VIDEO_STATUS,
            {"video_id": video_id, "status": "cancelled"},
        )

        await log.ainfo("pipeline_cancelled", jobs_cancelled=count)
        return count

    async def retry_failed(self, video_id: uuid.UUID) -> list[str]:
        """Reset all dead_letter/failed jobs back to pending.

        Returns the list of stage names that were reset.
        """
        cur = await self._db.execute(RETRY_FAILED_JOBS, {"video_id": video_id})
        rows = await cur.fetchall()
        stages = [str(r["stage"]) for r in rows]

        if stages:
            # Reset video status from failed back to media_generating
            await self._db.execute(
                UPDATE_VIDEO_STATUS,
                {"video_id": video_id, "status": "media_generating"},
            )

        await logger.ainfo(
            "jobs_retried",
            video_id=str(video_id),
            stages=stages,
        )
        return stages

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _create_job(
        self,
        video_id: uuid.UUID,
        stage: str,
        payload: dict[str, Any],
        priority: int = 0,
    ) -> dict[str, Any]:
        """Insert a new pipeline_jobs row."""
        cur = await self._db.execute(
            CREATE_JOB,
            {
                "video_id": video_id,
                "stage": stage,
                "payload": json.dumps(payload),
                "priority": priority,
            },
        )
        row = await cur.fetchone()
        await logger.ainfo(
            "job_created",
            video_id=str(video_id),
            stage=stage,
            job_id=row["id"] if row else None,
        )
        return dict(row) if row else {}

    async def _get_completed_stages(self, video_id: uuid.UUID) -> set[str]:
        """Return the set of stage names that have completed."""
        cur = await self._db.execute(GET_COMPLETED_STAGES, {"video_id": video_id})
        rows = await cur.fetchall()
        return {str(r["stage"]) for r in rows}

    async def _get_enqueued_stages(self, video_id: uuid.UUID) -> set[str]:
        """Return stages that already have a non-dead-letter job."""
        cur = await self._db.execute(GET_ENQUEUED_STAGES, {"video_id": video_id})
        rows = await cur.fetchall()
        return {str(r["stage"]) for r in rows}

    async def _get_completed_results(self, video_id: uuid.UUID) -> dict[str, dict[str, Any]]:
        """Return {stage_name: result_json} for all completed stages."""
        cur = await self._db.execute(GET_COMPLETED_STAGES, {"video_id": video_id})
        rows = await cur.fetchall()
        results: dict[str, dict[str, Any]] = {}
        for r in rows:
            result: Any = r["result"]
            if isinstance(result, str):
                result = json.loads(result)
            results[str(r["stage"])] = result or {}
        return results

    async def _update_video_status(self, video_id: uuid.UUID, completed_stage: str) -> None:
        """Map a stage completion to a video status transition."""
        # Direct stage→status mappings
        if completed_stage in _STAGE_TO_VIDEO_STATUS:
            new_status = _STAGE_TO_VIDEO_STATUS[completed_stage]
            await self._db.execute(
                UPDATE_VIDEO_STATUS,
                {"video_id": video_id, "status": new_status},
            )
            return

        # Check if all media stages are done → "media_complete"
        if completed_stage in _MEDIA_STAGES:
            completed = await self._get_completed_stages(video_id)
            if _MEDIA_STAGES.issubset(completed | {completed_stage}):
                await self._db.execute(
                    UPDATE_VIDEO_STATUS,
                    {"video_id": video_id, "status": "media_complete"},
                )

    @staticmethod
    def _build_downstream_payload(
        target_stage: str,
        completed_results: dict[str, dict[str, Any]],
    ) -> dict[str, Any]:
        """Merge upstream results into a payload for the target stage."""
        payload: dict[str, Any] = {}
        deps = PIPELINE_STAGES[target_stage]["depends_on"]
        for dep in deps:
            if dep in completed_results:
                payload[dep] = completed_results[dep]
        return payload

    @staticmethod
    def get_dependents(stage: str) -> list[str]:
        """Return all stages that directly depend on the given stage."""
        return [name for name, config in PIPELINE_STAGES.items() if stage in config["depends_on"]]
