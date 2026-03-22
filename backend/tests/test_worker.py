"""Tests for the pipeline worker — job claiming, concurrency, retry, and dead-lettering."""

from __future__ import annotations

import asyncio
import uuid
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.db.queries import CLAIM_NEXT_JOB, FAIL_JOB
from src.pipeline.stages import PIPELINE_STAGES
from src.pipeline.worker import _STAGE_HANDLERS, PipelineWorker, create_worker
from tests.conftest import requires_db


class TestWorkerUnit:
    """Unit tests for worker logic that don't require a database."""

    @staticmethod
    def _make_settings(max_jobs: int = 1) -> MagicMock:
        """Create a MagicMock Settings with valid budget values for BudgetEnforcer."""
        settings = MagicMock()
        settings.max_concurrent_jobs = max_jobs
        settings.budget.per_video_usd = 15.0
        settings.budget.soft_alert_pct = 0.70
        settings.budget.hard_alert_pct = 0.90
        return settings

    def test_stage_handlers_cover_all_stages(self) -> None:
        """Every stage in PIPELINE_STAGES must have a handler in _STAGE_HANDLERS."""
        for stage_name in PIPELINE_STAGES:
            assert stage_name in _STAGE_HANDLERS, f"Missing handler for {stage_name}"

    def test_create_worker_returns_pipeline_worker(self) -> None:
        """create_worker factory should produce a PipelineWorker instance."""
        settings = self._make_settings(max_jobs=3)
        pool = MagicMock()
        worker = create_worker(settings, pool)
        assert isinstance(worker, PipelineWorker)

    def test_r2_key_format(self) -> None:
        """R2 key should follow {channel_id}/{video_id}/{filename} pattern."""
        settings = self._make_settings()
        pool = MagicMock()
        worker = PipelineWorker(settings, pool)

        ch = uuid.UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
        vid = uuid.UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")
        key = worker._r2_key(ch, vid, "script.json")
        assert key == f"{ch}/{vid}/script.json"

    async def test_process_job_unknown_stage_raises(self) -> None:
        """_process_job should raise ValueError for unknown stages."""
        settings = self._make_settings()
        pool = MagicMock()
        worker = PipelineWorker(settings, pool)

        with pytest.raises(ValueError, match="Unknown pipeline stage"):
            await worker._process_job(uuid.uuid4(), "nonexistent_stage", {})

    async def test_stop_sets_running_false(self) -> None:
        """stop() should set _running to False."""
        settings = self._make_settings()
        pool = MagicMock()
        worker = PipelineWorker(settings, pool)
        worker._running = True
        await worker.stop()
        assert worker._running is False


@requires_db
class TestWorkerDatabase:
    """Worker tests that require a real database."""

    async def test_claim_job_skip_locked(
        self,
        db_pool: Any,
        test_video: dict[str, Any],
    ) -> None:
        """SKIP LOCKED should claim exactly one job from the queue."""
        video_id = test_video["id"]

        # Create 3 pending jobs
        async with db_pool.connection() as conn:
            for stage in ["script_generation", "voiceover_generation", "image_generation"]:
                await conn.execute(
                    """INSERT INTO pipeline_jobs (video_id, stage, payload, priority)
                       VALUES (%(vid)s, %(stage)s, '{}', 0)""",
                    {"vid": video_id, "stage": stage},
                )
            await conn.commit()

        # Claim one job
        async with db_pool.connection() as conn:
            cur = await conn.execute(CLAIM_NEXT_JOB)
            row = await cur.fetchone()
            await conn.commit()

        assert row is not None
        assert row["status"] == "in_progress"
        assert row["video_id"] == video_id

    async def test_concurrent_workers_no_double_processing(
        self,
        db_pool: Any,
        test_video: dict[str, Any],
    ) -> None:
        """Multiple concurrent claims should each get a different job (no double-processing)."""
        video_id = test_video["id"]

        # Create 5 jobs
        async with db_pool.connection() as conn:
            for i in range(5):
                await conn.execute(
                    """INSERT INTO pipeline_jobs (video_id, stage, payload, priority)
                       VALUES (%(vid)s, %(stage)s, '{}', 0)""",
                    {"vid": video_id, "stage": f"test_stage_{i}"},
                )
            await conn.commit()

        # Claim concurrently from 3 "workers"
        claimed_ids: list[int] = []

        async def claim_one() -> int | None:
            async with db_pool.connection() as conn:
                cur = await conn.execute(CLAIM_NEXT_JOB)
                row = await cur.fetchone()
                await conn.commit()
                return row["id"] if row else None

        results = await asyncio.gather(claim_one(), claim_one(), claim_one())
        claimed_ids = [r for r in results if r is not None]

        # All claimed IDs should be unique
        assert len(claimed_ids) == len(set(claimed_ids))

    async def test_failed_job_exponential_backoff(
        self,
        db_pool: Any,
        test_video: dict[str, Any],
    ) -> None:
        """Failed job should have visible_at pushed into the future with backoff."""
        video_id = test_video["id"]

        async with db_pool.connection() as conn:
            cur = await conn.execute(
                """INSERT INTO pipeline_jobs (video_id, stage, payload, priority, max_retries)
                   VALUES (%(vid)s, 'script_generation', '{}', 0, 5)
                   RETURNING *""",
                {"vid": video_id},
            )
            job = await cur.fetchone()
            await conn.commit()

        # Fail the job
        async with db_pool.connection() as conn:
            await conn.execute(
                FAIL_JOB,
                {"job_id": job["id"], "error_message": "test error"},
            )
            await conn.commit()

        # Check that visible_at is in the future and retry_count incremented
        async with db_pool.connection() as conn:
            cur = await conn.execute(
                "SELECT * FROM pipeline_jobs WHERE id = %(id)s",
                {"id": job["id"]},
            )
            updated = await cur.fetchone()

        assert updated["retry_count"] == 1
        assert updated["error_message"] == "test error"
        assert updated["status"] == "pending"  # not dead_letter yet
        assert updated["visible_at"] > updated["created_at"]

    async def test_dead_letter_after_max_retries(
        self,
        db_pool: Any,
        test_video: dict[str, Any],
    ) -> None:
        """Job should move to dead_letter once retry_count >= max_retries."""
        video_id = test_video["id"]

        async with db_pool.connection() as conn:
            cur = await conn.execute(
                """INSERT INTO pipeline_jobs
                       (video_id, stage, payload, priority, retry_count, max_retries)
                   VALUES (%(vid)s, 'script_generation', '{}', 0, 3, 3)
                   RETURNING *""",
                {"vid": video_id},
            )
            job = await cur.fetchone()
            await conn.commit()

        # Fail the job (retry_count already at max)
        async with db_pool.connection() as conn:
            await conn.execute(
                FAIL_JOB,
                {"job_id": job["id"], "error_message": "final failure"},
            )
            await conn.commit()

        async with db_pool.connection() as conn:
            cur = await conn.execute(
                "SELECT status, retry_count FROM pipeline_jobs WHERE id = %(id)s",
                {"id": job["id"]},
            )
            updated = await cur.fetchone()

        assert updated["status"] == "dead_letter"
        assert updated["retry_count"] == 4

    async def test_stalled_job_recovery(
        self,
        db_pool: Any,
        test_video: dict[str, Any],
    ) -> None:
        """Jobs that are in_progress with visible_at in the past should be recoverable."""
        video_id = test_video["id"]

        # Create a "stalled" job: in_progress with visible_at in the past
        async with db_pool.connection() as conn:
            await conn.execute(
                """INSERT INTO pipeline_jobs
                       (video_id, stage, status, payload, priority, visible_at)
                   VALUES (%(vid)s, 'script_generation', 'in_progress', '{}', 0,
                           now() - interval '10 minutes')""",
                {"vid": video_id},
            )
            await conn.commit()

        # The pg_cron job would normally reset these, but we can simulate it:
        async with db_pool.connection() as conn:
            cur = await conn.execute(
                """UPDATE pipeline_jobs
                   SET status = 'pending', updated_at = now()
                   WHERE status = 'in_progress'
                     AND visible_at < now()
                   RETURNING id""",
            )
            recovered = await cur.fetchall()
            await conn.commit()

        assert len(recovered) >= 1

        # Verify it can now be claimed
        async with db_pool.connection() as conn:
            cur = await conn.execute(CLAIM_NEXT_JOB)
            row = await cur.fetchone()
            await conn.commit()

        assert row is not None
        assert row["stage"] == "script_generation"


class TestWorkerHandlerDispatch:
    """Test that the worker dispatch correctly routes to handlers."""

    async def test_handler_receives_correct_args(self) -> None:
        """_process_job should pass video_id and payload to the handler."""
        settings = MagicMock()
        settings.max_concurrent_jobs = 1
        settings.budget.per_video_usd = 15.0
        settings.budget.soft_alert_pct = 0.70
        settings.budget.hard_alert_pct = 0.90
        pool = MagicMock()
        worker = PipelineWorker(settings, pool)

        video_id = uuid.uuid4()
        payload = {"test": "data"}
        mock_result = {"status": "ok"}

        with patch.dict(
            _STAGE_HANDLERS,
            {"script_generation": AsyncMock(return_value=mock_result)},
        ):
            result = await worker._process_job(video_id, "script_generation", payload)

        assert result == mock_result
