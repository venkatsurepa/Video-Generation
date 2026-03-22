"""Pipeline worker — polls the job queue and dispatches stage handlers.

Runs as a long-lived async task alongside the FastAPI server.  Claims jobs
from ``pipeline_jobs`` using ``SELECT ... FOR UPDATE SKIP LOCKED`` for safe
multi-worker concurrency.  Each stage handler orchestrates the relevant
service(s), uploads outputs to R2, and tracks costs.
"""

from __future__ import annotations

import asyncio
import json
import time
import traceback
from typing import TYPE_CHECKING, Any, cast

import httpx
import structlog

from src.db.queries import CLAIM_NEXT_JOB, COMPLETE_JOB, FAIL_JOB
from src.pipeline.handlers import STAGE_HANDLERS
from src.pipeline.orchestrator import Orchestrator
from src.pipeline.stages import PIPELINE_STAGES
from src.services.budget_enforcer import BudgetEnforcer
from src.services.health_monitor import HealthMonitor
from src.utils.circuit_breaker import CircuitBreaker
from src.utils.storage import R2Client

if TYPE_CHECKING:
    import uuid

    from psycopg import AsyncConnection
    from psycopg_pool import AsyncConnectionPool

    from src.config import Settings

logger = structlog.get_logger()

# Backward-compatible alias — canonical dict lives in src.pipeline.handlers
_STAGE_HANDLERS = STAGE_HANDLERS


class PipelineWorker:
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
        self._semaphore = asyncio.Semaphore(settings.max_concurrent_jobs)
        self._http: httpx.AsyncClient | None = None
        self._r2: R2Client | None = None
        self._monitor: HealthMonitor | None = None
        self._budget = BudgetEnforcer(settings, db_pool)
        self._tasks: set[asyncio.Task[None]] = set()
        self._circuits = {
            "anthropic": CircuitBreaker("anthropic", failure_threshold=3, recovery_timeout=120.0),
            "fish_audio": CircuitBreaker("fish_audio", failure_threshold=5, recovery_timeout=60.0),
            "fal_ai": CircuitBreaker("fal_ai", failure_threshold=5, recovery_timeout=60.0),
            "groq": CircuitBreaker("groq", failure_threshold=5, recovery_timeout=60.0),
            "youtube": CircuitBreaker("youtube", failure_threshold=3, recovery_timeout=300.0),
        }

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def start(self) -> None:
        """Start the worker polling loop."""
        self._running = True
        self._http = httpx.AsyncClient(timeout=120.0)
        self._r2 = R2Client(
            account_id=self._settings.storage.account_id,
            access_key_id=self._settings.storage.access_key_id,
            secret_access_key=self._settings.storage.secret_access_key,
            endpoint_url=self._settings.storage.endpoint_url,
        )
        self._monitor = HealthMonitor(self._settings, self._http)
        await logger.ainfo(
            "worker_started",
            max_concurrent=self._settings.max_concurrent_jobs,
            poll_interval=self._settings.pipeline_poll_interval_seconds,
        )
        while self._running:
            try:
                await self._poll_and_process()
            except Exception:
                await logger.aexception("worker_poll_error")
            await asyncio.sleep(self._settings.pipeline_poll_interval_seconds)

        # Wait for in-flight tasks on shutdown
        if self._tasks:
            await logger.ainfo("worker_draining", in_flight=len(self._tasks))
            await asyncio.gather(*self._tasks, return_exceptions=True)

        if self._http:
            await self._http.aclose()

    async def stop(self) -> None:
        """Signal the worker to stop after the current iteration."""
        self._running = False
        await logger.ainfo("worker_stopping")

    # ------------------------------------------------------------------
    # Poll loop
    # ------------------------------------------------------------------

    async def _poll_and_process(self) -> None:
        """Claim a job and dispatch it for processing under the semaphore."""
        async with self._pool.connection() as conn:
            cur = await conn.execute(CLAIM_NEXT_JOB)
            row = cast("dict[str, Any] | None", await cur.fetchone())
            if row is None:
                return
            await conn.commit()

        job_id: int = row["id"]
        video_id: uuid.UUID = row["video_id"]
        stage: str = row["stage"]
        payload: dict[str, Any] = row.get("payload") or {}
        if isinstance(payload, str):
            payload = json.loads(payload)

        log = logger.bind(job_id=job_id, video_id=str(video_id), stage=stage)
        await log.ainfo("job_claimed")

        # Run under semaphore to limit concurrency
        task = asyncio.create_task(self._run_with_semaphore(job_id, video_id, stage, payload))
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    async def _run_with_semaphore(
        self,
        job_id: int,
        video_id: uuid.UUID,
        stage: str,
        payload: dict[str, Any],
    ) -> None:
        """Execute a job under the concurrency semaphore with timeout."""
        assert self._monitor is not None

        async with self._semaphore:
            # Bind context so all nested service calls inherit video_id/stage
            structlog.contextvars.bind_contextvars(
                job_id=job_id,
                video_id=str(video_id),
                stage=stage,
            )
            try:
                await self._run_with_semaphore_inner(job_id, video_id, stage, payload)
            finally:
                structlog.contextvars.unbind_contextvars("job_id", "video_id", "stage")

    async def _run_with_semaphore_inner(
        self,
        job_id: int,
        video_id: uuid.UUID,
        stage: str,
        payload: dict[str, Any],
    ) -> None:
        """Inner body of _run_with_semaphore (extracted for contextvars cleanup)."""
        assert self._monitor is not None
        stage_config = PIPELINE_STAGES.get(stage, {})
        timeout = stage_config.get("timeout_seconds", 300)
        log = logger.bind(job_id=job_id, video_id=str(video_id), stage=stage)

        # Signal job start to Healthchecks.io
        await self._monitor.ping_start(stage)

        # Report current queue depth
        await self._report_queue_depth()

        # --- Budget enforcement ---
        budget_decision = await self._budget.check_budget(video_id, stage)
        if not budget_decision.allow:
            await log.awarning(
                "job_budget_refused",
                reason=budget_decision.reason,
                spend=str(budget_decision.spend.total_usd),
                budget=str(budget_decision.budget_usd),
            )
            await self._handle_failure(
                job_id,
                video_id,
                stage,
                RuntimeError(f"Budget exceeded: {budget_decision.reason}"),
            )
            await self._monitor.ping_failure(stage, "Budget exceeded")
            return

        # Apply degradation plan to payload if needed
        if budget_decision.degradation.level.value != "none":
            BudgetEnforcer.enforce_degradation(
                budget_decision.degradation,
                stage,
                payload,
            )

        t0 = time.monotonic()
        try:
            result = await asyncio.wait_for(
                self._process_job(video_id, stage, payload),
                timeout=timeout,
            )
            elapsed = round(time.monotonic() - t0, 2)
            await log.ainfo("job_succeeded", elapsed_seconds=elapsed)
            await self._handle_success(job_id, video_id, stage, result)

            await self._monitor.ping_success(stage)
            await self._monitor.report_metric(
                f"job_duration_seconds.{stage}",
                elapsed,
            )

            # Report cost if present in result
            cost_str = result.get("cost_usd")
            if cost_str:
                await self._monitor.report_metric(
                    f"job_cost_usd.{stage}",
                    float(cost_str),
                )

        except TimeoutError:
            elapsed = round(time.monotonic() - t0, 2)
            await log.aerror(
                "job_timeout",
                timeout_seconds=timeout,
                elapsed_seconds=elapsed,
            )
            await self._handle_failure(
                job_id,
                video_id,
                stage,
                TimeoutError(f"Stage {stage} timed out after {timeout}s"),
            )
            await self._monitor.ping_failure(
                stage,
                f"Timeout after {timeout}s",
            )
        except Exception as exc:
            elapsed = round(time.monotonic() - t0, 2)
            await log.aerror(
                "job_failed",
                error=str(exc),
                elapsed_seconds=elapsed,
            )
            await self._handle_failure(job_id, video_id, stage, exc)
            await self._monitor.ping_failure(stage, str(exc)[:500])

    # ------------------------------------------------------------------
    # Job dispatch
    # ------------------------------------------------------------------

    async def _process_job(
        self,
        video_id: uuid.UUID,
        stage: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        """Route to the correct stage handler."""
        handler = _STAGE_HANDLERS.get(stage)
        if handler is None:
            raise ValueError(f"Unknown pipeline stage: {stage}")
        result: dict[str, Any] = await handler(self, video_id, payload)
        return result

    # ------------------------------------------------------------------
    # Success / failure handlers
    # ------------------------------------------------------------------

    async def _handle_success(
        self,
        job_id: int,
        video_id: uuid.UUID,
        stage: str,
        result: dict[str, Any],
    ) -> None:
        """Mark job completed and advance the pipeline."""
        async with self._pool.connection() as conn:
            await conn.execute(
                COMPLETE_JOB,
                {"job_id": job_id, "result": json.dumps(result)},
            )
            orchestrator = Orchestrator(cast("AsyncConnection[dict[str, object]]", conn))
            await orchestrator.advance_pipeline(video_id, stage, result)
            await conn.commit()

    async def _handle_failure(
        self,
        job_id: int,
        video_id: uuid.UUID,
        stage: str,
        error: BaseException,
    ) -> None:
        """Record failure with exponential backoff retry logic."""
        error_msg = f"{type(error).__name__}: {error}"
        tb = traceback.format_exception(type(error), error, error.__traceback__)
        log = logger.bind(job_id=job_id, video_id=str(video_id), stage=stage)
        await log.aerror("job_error_detail", traceback="".join(tb[-3:]))

        async with self._pool.connection() as conn:
            await conn.execute(
                FAIL_JOB,
                {"job_id": job_id, "error_message": error_msg[:2000]},
            )
            await conn.commit()

    async def _report_queue_depth(self) -> None:
        """Emit queue depth metric for Grafana dashboards."""
        if self._monitor is None:
            return
        try:
            async with self._pool.connection() as conn:
                cur = await conn.execute(
                    "SELECT COUNT(*) AS n FROM pipeline_jobs WHERE status = 'pending'"
                )
                row = cast("dict[str, Any] | None", await cur.fetchone())
                depth = row["n"] if row else 0
            await self._monitor.report_metric("queue_depth_pending", float(depth))
        except Exception:
            pass  # never block pipeline for monitoring

    # ------------------------------------------------------------------
    # R2 helpers
    # ------------------------------------------------------------------

    def _r2_key(self, channel_id: uuid.UUID, video_id: uuid.UUID, filename: str) -> str:
        """Build R2 object key: {channel_id}/{video_id}/{filename}."""
        return f"{channel_id}/{video_id}/{filename}"

    async def _upload_to_r2(
        self,
        channel_id: uuid.UUID,
        video_id: uuid.UUID,
        filename: str,
        local_path: str,
        content_type: str = "application/octet-stream",
    ) -> str:
        """Upload a file to R2 with retry and fallback. Returns the object key."""
        assert self._r2 is not None
        key = self._r2_key(channel_id, video_id, filename)
        return await self._r2.upload_file_resilient(
            bucket=self._settings.storage.bucket_name,
            key=key,
            file_path=local_path,
            content_type=content_type,
        )

    def _download_from_r2(
        self,
        r2_key: str,
        local_path: str,
    ) -> str:
        """Download from R2 to local path. Returns local path."""
        assert self._r2 is not None
        self._r2.download_file(
            bucket=self._settings.storage.bucket_name,
            key=r2_key,
            destination=local_path,
        )
        return local_path

    async def _get_video_info(self, video_id: uuid.UUID) -> dict[str, Any]:
        """Fetch video + channel info from DB."""
        from src.db.queries import GET_VIDEO_WITH_CHANNEL

        async with self._pool.connection() as conn:
            cur = await conn.execute(GET_VIDEO_WITH_CHANNEL, {"video_id": video_id})
            row = await cur.fetchone()
            if row is None:
                raise ValueError(f"Video {video_id} not found")
            return dict(row)


def create_worker(
    settings: Settings,
    db_pool: AsyncConnectionPool,
) -> PipelineWorker:
    """Factory function to create a configured PipelineWorker."""
    return PipelineWorker(settings=settings, db_pool=db_pool)
