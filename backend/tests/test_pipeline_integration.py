"""End-to-end pipeline integration tests.

These test the full flow from topic input through the pipeline stages.
They require a real database connection and test the orchestrator + worker
coordination without making real API calls (services are mocked).

Run with: pytest tests/test_pipeline_integration.py -v
Run with real APIs: pytest tests/test_pipeline_integration.py -v -m integration
"""

from __future__ import annotations

import json
from typing import Any

from src.db.queries import (
    COMPLETE_JOB,
    GET_PIPELINE_JOBS,
)
from src.pipeline.orchestrator import Orchestrator
from tests.conftest import requires_db


@requires_db
class TestOrchestratorIntegration:
    """Test orchestrator with a real database."""

    async def test_start_pipeline_enqueues_root_stages(
        self,
        db_pool: Any,
        test_video: dict[str, Any],
    ) -> None:
        """start_pipeline should create jobs for stages with no dependencies."""
        video_id = test_video["id"]

        async with db_pool.connection() as conn:
            orchestrator = Orchestrator(conn)
            enqueued = await orchestrator.start_pipeline(video_id)
            await conn.commit()

        assert enqueued == ["script_generation"]

        # Verify job was created in DB
        async with db_pool.connection() as conn:
            cur = await conn.execute(GET_PIPELINE_JOBS, {"video_id": video_id})
            jobs = await cur.fetchall()

        assert len(jobs) == 1
        assert jobs[0]["stage"] == "script_generation"
        assert jobs[0]["status"] == "pending"

    async def test_start_pipeline_sets_video_status(
        self,
        db_pool: Any,
        test_video: dict[str, Any],
    ) -> None:
        """start_pipeline should set video status to media_generating."""
        video_id = test_video["id"]

        async with db_pool.connection() as conn:
            orchestrator = Orchestrator(conn)
            await orchestrator.start_pipeline(video_id)
            await conn.commit()

        async with db_pool.connection() as conn:
            cur = await conn.execute(
                "SELECT status FROM videos WHERE id = %(id)s", {"id": video_id}
            )
            row = await cur.fetchone()

        assert row is not None
        assert row["status"] == "media_generating"

    async def test_advance_pipeline_enqueues_dependents(
        self,
        db_pool: Any,
        test_video: dict[str, Any],
    ) -> None:
        """Completing script_generation should enqueue its 4 dependents."""
        video_id = test_video["id"]

        async with db_pool.connection() as conn:
            orchestrator = Orchestrator(conn)
            await orchestrator.start_pipeline(video_id)
            await conn.commit()

        # Simulate script_generation completing
        async with db_pool.connection() as conn:
            cur = await conn.execute(GET_PIPELINE_JOBS, {"video_id": video_id})
            jobs = await cur.fetchall()
            script_job = jobs[0]

            await conn.execute(
                COMPLETE_JOB,
                {"job_id": script_job["id"], "result": json.dumps({"script_text": "test"})},
            )
            await conn.commit()

        # Now advance
        async with db_pool.connection() as conn:
            orchestrator = Orchestrator(conn)
            newly_enqueued = await orchestrator.advance_pipeline(
                video_id, "script_generation", {"script_text": "test"}
            )
            await conn.commit()

        # script_generation has 4 dependents: voiceover, images, music, thumbnail
        expected = {
            "voiceover_generation",
            "image_generation",
            "music_selection",
            "thumbnail_generation",
        }
        assert set(newly_enqueued) == expected

    async def test_advance_pipeline_waits_for_all_deps(
        self,
        db_pool: Any,
        test_video: dict[str, Any],
    ) -> None:
        """audio_processing should NOT be enqueued until both voiceover AND music complete."""
        video_id = test_video["id"]

        async with db_pool.connection() as conn:
            orchestrator = Orchestrator(conn)
            await orchestrator.start_pipeline(video_id)
            await conn.commit()

        # Complete script_generation
        async with db_pool.connection() as conn:
            cur = await conn.execute(GET_PIPELINE_JOBS, {"video_id": video_id})
            jobs = await cur.fetchall()
            await conn.execute(
                COMPLETE_JOB,
                {"job_id": jobs[0]["id"], "result": json.dumps({})},
            )
            orchestrator = Orchestrator(conn)
            await orchestrator.advance_pipeline(video_id, "script_generation")
            await conn.commit()

        # Complete only voiceover_generation (music not done yet)
        async with db_pool.connection() as conn:
            cur = await conn.execute(GET_PIPELINE_JOBS, {"video_id": video_id})
            jobs = await cur.fetchall()
            vo_job = next(j for j in jobs if j["stage"] == "voiceover_generation")
            await conn.execute(
                COMPLETE_JOB,
                {"job_id": vo_job["id"], "result": json.dumps({"voiceover_r2_key": "test"})},
            )
            orchestrator = Orchestrator(conn)
            enqueued = await orchestrator.advance_pipeline(video_id, "voiceover_generation")
            await conn.commit()

        # audio_processing should NOT be enqueued (music_selection still pending)
        assert "audio_processing" not in enqueued
        # But caption_generation should be (only depends on voiceover)
        assert "caption_generation" in enqueued

    async def test_cancel_pipeline(
        self,
        db_pool: Any,
        test_video: dict[str, Any],
    ) -> None:
        """cancel_pipeline should fail all pending/in_progress jobs."""
        video_id = test_video["id"]

        async with db_pool.connection() as conn:
            orchestrator = Orchestrator(conn)
            await orchestrator.start_pipeline(video_id)
            await conn.commit()

        async with db_pool.connection() as conn:
            orchestrator = Orchestrator(conn)
            count = await orchestrator.cancel_pipeline(video_id)
            await conn.commit()

        assert count == 1

        async with db_pool.connection() as conn:
            cur = await conn.execute(
                "SELECT status FROM videos WHERE id = %(id)s", {"id": video_id}
            )
            row = await cur.fetchone()

        assert row is not None
        assert row["status"] == "cancelled"

    async def test_cancel_preserves_completed_jobs(
        self,
        db_pool: Any,
        test_video: dict[str, Any],
    ) -> None:
        """Cancellation should not affect already-completed jobs."""
        video_id = test_video["id"]

        # Start and complete script
        async with db_pool.connection() as conn:
            orchestrator = Orchestrator(conn)
            await orchestrator.start_pipeline(video_id)
            await conn.commit()

        async with db_pool.connection() as conn:
            cur = await conn.execute(GET_PIPELINE_JOBS, {"video_id": video_id})
            jobs = await cur.fetchall()
            await conn.execute(
                COMPLETE_JOB,
                {"job_id": jobs[0]["id"], "result": json.dumps({})},
            )
            orchestrator = Orchestrator(conn)
            await orchestrator.advance_pipeline(video_id, "script_generation")
            await conn.commit()

        # Now cancel
        async with db_pool.connection() as conn:
            orchestrator = Orchestrator(conn)
            await orchestrator.cancel_pipeline(video_id)
            await conn.commit()

        # Verify completed job is still completed
        async with db_pool.connection() as conn:
            cur = await conn.execute(GET_PIPELINE_JOBS, {"video_id": video_id})
            all_jobs = await cur.fetchall()

        completed = [j for j in all_jobs if j["status"] == "completed"]
        failed = [j for j in all_jobs if j["status"] == "failed"]

        assert len(completed) == 1
        assert completed[0]["stage"] == "script_generation"
        assert len(failed) >= 1

    async def test_parallel_stage_execution(
        self,
        db_pool: Any,
        test_video: dict[str, Any],
    ) -> None:
        """After script_generation, all 4 parallel stages should be enqueued at once."""
        video_id = test_video["id"]

        async with db_pool.connection() as conn:
            orchestrator = Orchestrator(conn)
            await orchestrator.start_pipeline(video_id)
            await conn.commit()

        # Complete script
        async with db_pool.connection() as conn:
            cur = await conn.execute(GET_PIPELINE_JOBS, {"video_id": video_id})
            jobs = await cur.fetchall()
            await conn.execute(
                COMPLETE_JOB,
                {"job_id": jobs[0]["id"], "result": json.dumps({"script_text": "test"})},
            )
            orchestrator = Orchestrator(conn)
            enqueued = await orchestrator.advance_pipeline(video_id, "script_generation")
            await conn.commit()

        # All 4 stages should be enqueued simultaneously
        assert len(enqueued) == 4
        assert set(enqueued) == {
            "voiceover_generation",
            "image_generation",
            "music_selection",
            "thumbnail_generation",
        }

        # Verify all are in pending status
        async with db_pool.connection() as conn:
            cur = await conn.execute(GET_PIPELINE_JOBS, {"video_id": video_id})
            all_jobs = await cur.fetchall()

        pending = [j for j in all_jobs if j["status"] == "pending"]
        assert len(pending) == 4

    async def test_get_pipeline_status(
        self,
        db_pool: Any,
        test_video: dict[str, Any],
    ) -> None:
        """get_pipeline_status should return video status and all jobs."""
        video_id = test_video["id"]

        async with db_pool.connection() as conn:
            orchestrator = Orchestrator(conn)
            await orchestrator.start_pipeline(video_id)
            await conn.commit()

        async with db_pool.connection() as conn:
            orchestrator = Orchestrator(conn)
            status = await orchestrator.get_pipeline_status(video_id)

        assert status.video_id == video_id
        assert status.video_status == "media_generating"
        assert len(status.jobs) == 1
        assert status.jobs[0].stage == "script_generation"

    async def test_retry_failed_jobs(
        self,
        db_pool: Any,
        test_video: dict[str, Any],
    ) -> None:
        """retry_failed should reset dead_letter jobs to pending."""
        video_id = test_video["id"]

        # Create a dead_letter job
        async with db_pool.connection() as conn:
            await conn.execute(
                """INSERT INTO pipeline_jobs (video_id, stage, status, payload, retry_count, max_retries)
                   VALUES (%(vid)s, 'script_generation', 'dead_letter', '{}', 3, 3)""",
                {"vid": video_id},
            )
            await conn.execute(
                "UPDATE videos SET status = 'failed' WHERE id = %(id)s",
                {"id": video_id},
            )
            await conn.commit()

        async with db_pool.connection() as conn:
            orchestrator = Orchestrator(conn)
            retried = await orchestrator.retry_failed(video_id)
            await conn.commit()

        assert "script_generation" in retried

        # Verify video status reset
        async with db_pool.connection() as conn:
            cur = await conn.execute(
                "SELECT status FROM videos WHERE id = %(id)s", {"id": video_id}
            )
            row = await cur.fetchone()

        assert row is not None
        assert row["status"] == "media_generating"


@requires_db
class TestPipelineStatusTransitions:
    """Test that video status transitions correctly through the pipeline."""

    async def test_script_generation_sets_script_generated(
        self,
        db_pool: Any,
        test_video: dict[str, Any],
    ) -> None:
        video_id = test_video["id"]

        async with db_pool.connection() as conn:
            orchestrator = Orchestrator(conn)
            await orchestrator.start_pipeline(video_id)
            # Complete script
            cur = await conn.execute(GET_PIPELINE_JOBS, {"video_id": video_id})
            jobs = await cur.fetchall()
            await conn.execute(
                COMPLETE_JOB,
                {"job_id": jobs[0]["id"], "result": json.dumps({})},
            )
            await orchestrator.advance_pipeline(video_id, "script_generation")
            await conn.commit()

        async with db_pool.connection() as conn:
            cur = await conn.execute(
                "SELECT status FROM videos WHERE id = %(id)s", {"id": video_id}
            )
            row = await cur.fetchone()

        assert row["status"] == "script_generated"

    async def test_video_assembly_sets_assembled(
        self,
        db_pool: Any,
        test_video: dict[str, Any],
    ) -> None:
        video_id = test_video["id"]

        async with db_pool.connection() as conn:
            orchestrator = Orchestrator(conn)
            await orchestrator._update_video_status(video_id, "video_assembly")
            await conn.commit()

        async with db_pool.connection() as conn:
            cur = await conn.execute(
                "SELECT status FROM videos WHERE id = %(id)s", {"id": video_id}
            )
            row = await cur.fetchone()

        assert row["status"] == "assembled"

    async def test_youtube_upload_sets_published(
        self,
        db_pool: Any,
        test_video: dict[str, Any],
    ) -> None:
        video_id = test_video["id"]

        async with db_pool.connection() as conn:
            orchestrator = Orchestrator(conn)
            await orchestrator._update_video_status(video_id, "youtube_upload")
            await conn.commit()

        async with db_pool.connection() as conn:
            cur = await conn.execute(
                "SELECT status FROM videos WHERE id = %(id)s", {"id": video_id}
            )
            row = await cur.fetchone()

        assert row["status"] == "published"
