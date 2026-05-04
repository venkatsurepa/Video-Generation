# Best-effort cleanup blocks (try/except/pass for tmp file unlink, channel
# DELETE on partial flow) and a NamedTemporaryFile that needs delete=False
# are intentional here. POLL_INTERVAL/MAX_POLL_MINUTES are local "constants".
# ruff: noqa: SIM105, SIM115, N806, TC003
"""End-to-end production validation for the CrimeMill + Street Level pipeline.

Runs eight integration tests against live services:

  1. Railway health check             (Railway → FastAPI)
  2. Railway → Supabase connectivity  (Railway → FastAPI → Postgres)
  3. Remotion Lambda render           (local → AWS Lambda → S3)
  4. Street Level travel script       (local → Anthropic Sonnet/Haiku)
  5. CrimeMill crime script           (local → Anthropic Sonnet)
  6. Cloudflare R2 round-trip         (local → R2)
  7. Channel CRUD via Railway API     (Railway → Postgres)
  8. End-to-end pipeline trigger      (Railway + worker + all services)

Usage (from backend/):
    python scripts/production_validation.py
    python scripts/production_validation.py --only 4,5,6
    python scripts/production_validation.py --skip 7,8
    python scripts/production_validation.py --railway-url https://your.app

Tests 1, 2, 7, 8 require RAILWAY_URL (env var or --railway-url flag). Tests
3-6 run entirely against local environment + external APIs.

Output:
    - Per-test PASS / FAIL / SKIP with details
    - Cost totals where available (Anthropic only — other services don't
      return per-call cost)
    - Markdown report written to docs/PRODUCTION_VALIDATION_RESULTS.md
    - Exit code: 0 if all non-skipped tests pass, 1 otherwise
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import subprocess
import sys
import tempfile
import time
import traceback
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path
from typing import Any

BACKEND_DIR = Path(__file__).resolve().parent.parent
REPO_ROOT = BACKEND_DIR.parent
VIDEO_DIR = REPO_ROOT / "video"
DOCS_DIR = REPO_ROOT / "docs"
FIXTURE_PATH = BACKEND_DIR / "fixtures" / "rhyo_reports" / "hyderabad_banjara_hills.md"

sys.path.insert(0, str(BACKEND_DIR))


# ============================================================================
# Test result framework
# ============================================================================


@dataclass
class TestResult:
    test_id: int
    name: str
    status: str  # PASS | FAIL | SKIP
    duration_s: float
    cost_usd: Decimal = Decimal("0")
    details: dict[str, Any] = field(default_factory=dict)
    error: str | None = None
    suggested_fix: str | None = None


RESULTS: list[TestResult] = []
START_TIME = time.monotonic()


def log(msg: str) -> None:
    elapsed = time.monotonic() - START_TIME
    print(f"[{elapsed:7.2f}s] {msg}", flush=True)


async def run_test(
    test_id: int,
    name: str,
    fn: Callable[[], Awaitable[TestResult]],
) -> TestResult:
    log(f"=== TEST {test_id}: {name} ===")
    t0 = time.monotonic()
    try:
        result = await fn()
        result.test_id = test_id
        result.name = name
        result.duration_s = time.monotonic() - t0
    except Exception as exc:
        result = TestResult(
            test_id=test_id,
            name=name,
            status="FAIL",
            duration_s=time.monotonic() - t0,
            error=f"{type(exc).__name__}: {exc}\n{traceback.format_exc()}",
        )

    emoji = {"PASS": "PASS", "FAIL": "FAIL", "SKIP": "SKIP"}[result.status]
    log(f"    [{emoji}] {name} ({result.duration_s:.1f}s, ${result.cost_usd})")
    if result.error:
        first_line = result.error.strip().splitlines()[0]
        log(f"    error: {first_line[:200]}")
    if result.status == "PASS" and result.details:
        preview = {k: v for k, v in list(result.details.items())[:5]}
        log(f"    details: {preview}")
    RESULTS.append(result)
    return result


# ============================================================================
# Helpers
# ============================================================================


def get_railway_url(override: str | None) -> str | None:
    return override or os.environ.get("RAILWAY_URL") or None


def skip(msg: str, fix: str | None = None) -> TestResult:
    return TestResult(
        test_id=0,
        name="",
        status="SKIP",
        duration_s=0.0,
        details={"reason": msg},
        suggested_fix=fix,
    )


def fail(error: str, fix: str | None = None, details: dict | None = None) -> TestResult:
    return TestResult(
        test_id=0,
        name="",
        status="FAIL",
        duration_s=0.0,
        error=error,
        suggested_fix=fix,
        details=details or {},
    )


def passed(details: dict, cost: Decimal = Decimal("0")) -> TestResult:
    return TestResult(
        test_id=0,
        name="",
        status="PASS",
        duration_s=0.0,
        details=details,
        cost_usd=cost,
    )


# ============================================================================
# Test 1: Railway /health
# ============================================================================


async def test_01_railway_health(railway_url: str | None) -> TestResult:
    if not railway_url:
        return skip(
            "RAILWAY_URL not set",
            "Export RAILWAY_URL or pass --railway-url https://your-service.up.railway.app",
        )

    import httpx

    url = f"{railway_url.rstrip('/')}/health"
    last_exc: Exception | None = None
    r = None
    # First call sometimes hits cold DNS / TLS setup on Windows; retry once.
    for attempt in (1, 2):
        try:
            async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
                r = await client.get(url)
            break
        except Exception as exc:
            last_exc = exc
            if attempt == 1:
                log(f"    attempt 1 failed ({type(exc).__name__}); retrying once")
                await asyncio.sleep(2)
    if r is None:
        return fail(
            f"HTTP request failed after retry: {type(last_exc).__name__}: {last_exc!r}",
            "Check that RAILWAY_URL is correct and Railway deployment is live",
            {"url": url},
        )

    if r.status_code != 200:
        return fail(
            f"Expected 200, got {r.status_code}",
            "Check Railway deploy logs; /health returns 503 if DB unreachable",
            {"url": url, "status": r.status_code, "body": r.text[:500]},
        )

    try:
        body = r.json()
    except Exception:
        return fail(
            "Response is not JSON",
            "Check /health endpoint is returning HealthResponse JSON",
            {"url": url, "body": r.text[:500]},
        )

    if "status" not in body:
        return fail(
            "Response JSON missing 'status' field",
            "Check HealthResponse pydantic model",
            {"body": body},
        )

    return passed({
        "url": url,
        "status": body.get("status"),
        "environment": body.get("environment"),
        "db": body.get("db"),
        "r2": body.get("r2"),
        "queue_depth": body.get("queue_depth"),
    })


# ============================================================================
# Test 2: Railway can reach Supabase (via /health db field)
# ============================================================================


async def test_02_railway_supabase(railway_url: str | None) -> TestResult:
    if not railway_url:
        return skip(
            "RAILWAY_URL not set",
            "Export RAILWAY_URL or pass --railway-url",
        )

    import httpx

    url = f"{railway_url.rstrip('/')}/health"
    last_exc: Exception | None = None
    r = None
    for attempt in (1, 2):
        try:
            async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
                r = await client.get(url)
            break
        except Exception as exc:
            last_exc = exc
            if attempt == 1:
                log(f"    attempt 1 failed ({type(exc).__name__}); retrying once")
                await asyncio.sleep(2)
    if r is None:
        return fail(
            f"HTTP request failed after retry: {type(last_exc).__name__}: {last_exc!r}",
            "Railway not reachable",
            {"url": url},
        )

    if r.status_code != 200:
        return fail(
            f"/health returned {r.status_code}",
            "Fix /health first (Test 1)",
            {"status": r.status_code, "body": r.text[:500]},
        )

    body = r.json()
    db_status = body.get("db")
    db_pool = body.get("db_pool")

    if db_status != "connected":
        return fail(
            f"db_status='{db_status}' — Railway cannot reach Supabase",
            "Set SUPABASE_DB_URL in Railway Variables to the Session Pooler URL "
            "(NOT the direct connection URL — direct is IPv6-only and Railway can't reach it). "
            "Get the pooler URL from Supabase dashboard → Connect → Session pooler.",
            {"db": db_status, "db_pool": db_pool},
        )

    return passed({
        "db": db_status,
        "db_pool": db_pool,
        "queue_depth": body.get("queue_depth"),
    })


# ============================================================================
# Test 3: Remotion Lambda render
# ============================================================================


async def test_03_remotion_render() -> TestResult:
    from src.config import get_settings

    s = get_settings()

    if not s.remotion.aws_access_key_id or not s.remotion.aws_secret_access_key:
        return skip(
            "REMOTION_AWS_ACCESS_KEY_ID / REMOTION_AWS_SECRET_ACCESS_KEY not set",
            "Add to backend/.env",
        )
    if not s.remotion.lambda_function_name or not s.remotion.serve_url:
        return skip(
            "REMOTION_LAMBDA_FUNCTION_NAME / REMOTION_SERVE_URL not set",
            "Add to backend/.env",
        )
    if not VIDEO_DIR.exists():
        return fail(f"video/ directory not found at {VIDEO_DIR}")

    # Pre-check: confirm the Lambda function actually exists. Without this,
    # a missing function causes Remotion to retry inside the AWS SDK for the
    # full Lambda timeout (~5 min) before reporting ResourceNotFoundException.
    try:
        import boto3
        from botocore.exceptions import ClientError

        lam = boto3.client(
            "lambda",
            region_name=s.remotion.aws_region,
            aws_access_key_id=s.remotion.aws_access_key_id,
            aws_secret_access_key=s.remotion.aws_secret_access_key,
        )
        try:
            lam.get_function(FunctionName=s.remotion.lambda_function_name)
        except ClientError as exc:
            err_code = exc.response.get("Error", {}).get("Code", "")
            if err_code == "ResourceNotFoundException":
                # List what's actually deployed for the user's report
                try:
                    fns = lam.list_functions()
                    remotion_fns = [
                        f["FunctionName"]
                        for f in fns.get("Functions", [])
                        if f["FunctionName"].startswith("remotion-render")
                    ]
                except Exception:
                    remotion_fns = []
                return fail(
                    f"Lambda function '{s.remotion.lambda_function_name}' "
                    f"does not exist in {s.remotion.aws_region}",
                    "Deploy the function: cd video && npx remotion lambda functions deploy. "
                    "Then update REMOTION_LAMBDA_FUNCTION_NAME in backend/.env to the deployed name.",
                    {
                        "configured_function": s.remotion.lambda_function_name,
                        "region": s.remotion.aws_region,
                        "remotion_functions_in_region": remotion_fns,
                    },
                )
            raise
    except ImportError:
        log("    (boto3 not available — skipping pre-check)")

    # Set env vars on os.environ directly rather than passing via env=.
    # Windows subprocess env inheritance through .cmd shims (npx.cmd) is
    # unreliable — vars set on the child env dict may not reach the final
    # node.exe process. Mutating os.environ guarantees inheritance.
    os.environ["REMOTION_AWS_ACCESS_KEY_ID"] = s.remotion.aws_access_key_id
    os.environ["REMOTION_AWS_SECRET_ACCESS_KEY"] = s.remotion.aws_secret_access_key
    os.environ["AWS_ACCESS_KEY_ID"] = s.remotion.aws_access_key_id
    os.environ["AWS_SECRET_ACCESS_KEY"] = s.remotion.aws_secret_access_key
    os.environ["AWS_DEFAULT_REGION"] = s.remotion.aws_region

    # 30 frames = 1 second of video at 30fps. Cheapest possible render.
    import shutil

    npx_path = shutil.which("npx") or shutil.which("npx.cmd")
    if not npx_path:
        return fail(
            "npx not found in PATH",
            "Install Node.js + npm. On Windows the binary is usually npx.cmd",
        )

    # Full `lambda render` with frames=0-30 (1s @ 30fps) — exercises the
    # complete encode pipeline (AWS auth → Lambda → bundle → frame render →
    # ffmpeg encode → S3 MP4) at minimal cost (~$0.001-0.02 per run).
    cmd = [
        npx_path,
        "--yes",
        "remotion",
        "lambda",
        "render",
        f"--function-name={s.remotion.lambda_function_name}",
        f"--region={s.remotion.aws_region}",
        "--frames=0-30",
        "--props={}",
        "--log=verbose",
        s.remotion.serve_url,
        "CrimeDocumentary",
    ]

    log(f"    spawning: {' '.join(cmd)}")
    t0 = time.monotonic()
    # Merge stderr into stdout — Remotion CLI on Windows splits the error
    # message between fd1 and fd2 in a way that causes one side to be lost
    # to subprocess capture. Combining them recovers the full diagnostic.
    try:
        completed = await asyncio.to_thread(
            subprocess.run,
            cmd,
            cwd=str(VIDEO_DIR),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=False,
            timeout=600,
        )
    except subprocess.TimeoutExpired:
        return fail(
            "Remotion Lambda render timed out after 10 minutes",
            "Check AWS Lambda console for function logs; function may be cold or OOMing",
        )
    except FileNotFoundError as exc:
        return fail(
            f"npx not found: {exc}",
            "Install Node.js + npm; Remotion Lambda CLI requires npx",
        )

    duration = time.monotonic() - t0
    # stderr is merged into stdout; .stderr is None
    stdout = (completed.stdout or b"").decode("utf-8", errors="replace")
    stderr = ""
    proc_returncode = completed.returncode
    combined = stdout + "\n" + stderr

    if proc_returncode != 0:
        return fail(
            f"Remotion render exited with code {proc_returncode}",
            "Check stdout_tail/stderr_tail below for the underlying Lambda error. "
            "Common causes: bad serve URL, missing Lambda function, IAM policy gap, "
            "composition rendering error (often: missing required props), Lambda timeout.",
            {
                "duration_s": round(duration, 1),
                "stdout_tail": stdout[-4000:],
                "stderr_tail": stderr[-4000:],
            },
        )

    # Parse the S3 URL from stdout. `lambda render` prints an MP4 URL.
    import re

    ansi_stripped = re.sub(r"\x1b\[[0-9;]*m", "", combined)
    s3_url_match = re.search(
        r"https://[^\s\"']*remotionlambda[^\s\"']*\.mp4",
        ansi_stripped,
    )
    if not s3_url_match:
        return fail(
            "Could not parse MP4 URL from Remotion output",
            "Check stdout for the rendered file location; Lambda may have failed silently",
            {"stdout_tail": stdout[-2000:], "stderr_tail": stderr[-2000:]},
        )
    s3_url = s3_url_match.group(0)

    # Download the MP4 (not just HEAD) and verify it's >10KB
    import httpx

    try:
        async with httpx.AsyncClient(timeout=120.0, follow_redirects=True) as client:
            r = await client.get(s3_url)
            if r.status_code != 200:
                return fail(
                    f"MP4 URL returned {r.status_code} on GET",
                    "Check S3 object ACL / signed URL / region",
                    {"s3_url": s3_url, "status": r.status_code},
                )
            size = len(r.content)
    except Exception as exc:
        return fail(
            f"MP4 GET request failed: {exc}",
            "S3 object may be private or region mismatch",
            {"s3_url": s3_url},
        )

    if size < 10_000:
        return fail(
            f"MP4 is only {size} bytes (expected >10KB)",
            "Render likely failed silently; check Lambda CloudWatch logs",
            {"s3_url": s3_url, "size_bytes": size},
        )

    return passed({
        "s3_url": s3_url,
        "size_bytes": size,
        "render_seconds": round(duration, 1),
        "frames": "0-30 (1s @ 30fps)",
    })


# ============================================================================
# Test 4: Street Level travel script
# ============================================================================


async def test_04_travel_script() -> TestResult:
    """Run scripts/generate_travel_sample.py as subprocess, parse stdout."""
    from src.config import get_settings

    s = get_settings()
    if not s.anthropic.api_key:
        return skip("ANTHROPIC_API_KEY not set", "Add to backend/.env")

    sample_script = BACKEND_DIR / "scripts" / "generate_travel_sample.py"
    if not sample_script.exists():
        return fail(f"Sample script not found at {sample_script}")

    cmd = [sys.executable, str(sample_script)]
    log(f"    spawning: {sys.executable} scripts/generate_travel_sample.py")
    try:
        completed = await asyncio.to_thread(
            subprocess.run,
            cmd,
            cwd=str(BACKEND_DIR),
            capture_output=True,
            text=False,
            timeout=300,
        )
    except subprocess.TimeoutExpired:
        return fail(
            "generate_travel_sample.py timed out after 5 minutes",
            "Anthropic API may be slow; check API key + rate limits",
        )

    stdout = (completed.stdout or b"").decode("utf-8", errors="replace")
    stderr = (completed.stderr or b"").decode("utf-8", errors="replace")

    if completed.returncode != 0:
        return fail(
            f"generate_travel_sample.py exited with {completed.returncode}",
            "Check stderr for the underlying error (likely Anthropic auth or fixture path)",
            {"stdout_tail": stdout[-800:], "stderr_tail": stderr[-800:]},
        )

    import re

    wc_match = re.search(r"WORD COUNT\s*:\s*(\d+)", stdout)
    if not wc_match:
        return fail(
            "Could not parse 'WORD COUNT :' from sample script output",
            "Check that generate_travel_sample.py still prints 'WORD COUNT : N'",
            {"stdout_tail": stdout[-1500:]},
        )
    word_count = int(wc_match.group(1))

    # Brand rule: "Rhyo" / "rhyo" must NOT appear in the spoken script body
    # (Street Level brand is a channel-level concept, not a token to inject).
    # The sample script delimits the body between "FIRST 500 CHARS OF SCRIPT"
    # and the next "=" banner.
    body_match = re.search(
        r"FIRST 500 CHARS OF SCRIPT\s*\n-+\n(.*?)\n=+",
        stdout,
        flags=re.DOTALL,
    )
    script_body = body_match.group(1) if body_match else ""
    rhyo_in_body = "Rhyo" in script_body or "rhyo" in script_body

    # Sponsor credit rule: "Rhyo Security Solutions" SHOULD appear in the
    # description block (between "DESCRIPTION" header and the next banner).
    desc_match = re.search(
        r"DESCRIPTION\s*\n-+\n(.*?)\n=+",
        stdout,
        flags=re.DOTALL,
    )
    description_block = desc_match.group(1) if desc_match else ""
    has_sponsor_credit = "Rhyo Security Solutions" in description_block

    # Sum cost lines if present (SCRIPT COST / TITLE COST / DESC COST)
    total_cost = Decimal("0")
    for label in ("SCRIPT COST", "TITLE COST", "DESC COST"):
        m = re.search(rf"{label}\s*:\s*([\d.]+)", stdout)
        if m:
            try:
                total_cost += Decimal(m.group(1))
            except Exception:
                pass
    total_cost = total_cost.quantize(Decimal("0.000001"))

    problems: list[str] = []
    if word_count < 1400:
        problems.append(f"word_count={word_count} < 1400")
    if rhyo_in_body:
        problems.append("'Rhyo' leaked into spoken script body")
    if not has_sponsor_credit:
        problems.append("'Rhyo Security Solutions' missing from description sponsor credit")

    if problems:
        return fail(
            "; ".join(problems),
            "Travel-safety brand rules: narration must not mention Rhyo; description must credit Rhyo Security Solutions.",
            {"word_count": word_count, "stdout_tail": stdout[-1500:]},
        )

    title_match = re.search(r"TITLE\s*:\s*(.+)", stdout)
    return passed(
        {
            "word_count": word_count,
            "rhyo_excluded_from_script": True,
            "rhyo_in_description_credit": True,
            "title": (title_match.group(1).strip() if title_match else ""),
        },
        cost=total_cost,
    )


# ============================================================================
# Test 5: CrimeMill crime script
# ============================================================================


async def test_05_crime_script() -> TestResult:
    from src.config import get_settings

    s = get_settings()
    if not s.anthropic.api_key:
        return skip("ANTHROPIC_API_KEY not set", "Add to backend/.env")

    import httpx

    from src.models.script import ChannelSettings, TopicInput
    from src.services.script_generator import ScriptGenerator

    topic = TopicInput(
        topic="The Wirecard Scandal",
        video_length_minutes=25,
        rotation_index=0,
        angle="How a €1.9B accounting fraud went undetected for a decade",
        region="Germany",
        era="2002-2020",
    )
    channel = ChannelSettings(
        channel_name="CrimeMill",
        channel_id="production-validation",
        tone="dark, measured, cinematic",
        target_audience="true crime enthusiasts, 25-45",
        content_rating="TV-14",
    )

    async with httpx.AsyncClient() as http:
        gen = ScriptGenerator(s, http)
        try:
            script = await gen.generate_script(topic, channel)
        except Exception as exc:
            return fail(
                f"ScriptGenerator.generate_script raised: {exc}",
                "Check SCRIPT_SYSTEM_PROMPT + Anthropic API key + model name",
            )

    word_count = script.word_count
    cost = script.cost.cost_usd

    if word_count < 2000:
        return fail(
            f"word_count={word_count} < 2000",
            "Sonnet under-delivered on length; bump max_tokens or add explicit minimum",
            {
                "word_count": word_count,
                "hook_type": script.hook_type.value,
                "script_head": script.script_text[:400],
            },
        )

    return passed(
        {
            "word_count": word_count,
            "hook_type": script.hook_type.value,
            "open_loops": len(script.open_loops),
            "twists": len(script.twist_placements),
            "script_head": script.script_text[:200],
        },
        cost=cost,
    )


# ============================================================================
# Test 6: R2 round-trip
# ============================================================================


async def test_06_r2_round_trip() -> TestResult:
    from src.config import get_settings
    from src.utils.storage import R2Client

    s = get_settings()
    if not s.storage.access_key_id or not s.storage.secret_access_key:
        return skip(
            "R2_ACCESS_KEY_ID / R2_SECRET_ACCESS_KEY not set",
            "Add to backend/.env",
        )
    if not s.storage.bucket_name:
        return skip("R2_BUCKET_NAME not set", "Add to backend/.env")

    client = R2Client(
        account_id=s.storage.account_id,
        access_key_id=s.storage.access_key_id,
        secret_access_key=s.storage.secret_access_key,
        endpoint_url=s.storage.endpoint_url,
    )

    # HeadBucket reachability
    health = await client.health_check(s.storage.bucket_name)
    if not health.get("healthy"):
        return fail(
            f"R2 HeadBucket failed: {health.get('error')}",
            "Check R2 credentials, bucket name, and endpoint URL",
            {"health": health},
        )

    # Upload
    key = f"_validation/{uuid.uuid4().hex}.txt"
    payload = f"crimemill production validation {time.time()}".encode()
    tmp = tempfile.NamedTemporaryFile(mode="wb", suffix=".txt", delete=False)
    try:
        tmp.write(payload)
        tmp.close()
        tmp_path = tmp.name

        await asyncio.to_thread(
            client.upload_file,
            s.storage.bucket_name,
            key,
            tmp_path,
            "text/plain",
        )

        # Presigned download URL
        presigned = await asyncio.to_thread(
            client.generate_presigned_url,
            s.storage.bucket_name,
            key,
            300,
        )

        # Download via URL
        import httpx

        async with httpx.AsyncClient(timeout=30.0) as http:
            r = await http.get(presigned)
            if r.status_code != 200:
                return fail(
                    f"Presigned download returned {r.status_code}",
                    "Check R2 endpoint + signed URL generation",
                    {"status": r.status_code, "key": key},
                )
            downloaded = r.content

        if downloaded != payload:
            return fail(
                "Downloaded content does not match uploaded payload",
                "R2 content integrity issue — possible partial write",
                {"uploaded_len": len(payload), "downloaded_len": len(downloaded)},
            )

        # Delete
        await asyncio.to_thread(client.delete_file, s.storage.bucket_name, key)

        # Verify delete
        exists = await asyncio.to_thread(client.file_exists, s.storage.bucket_name, key)
        if exists:
            return fail(
                "File still exists after delete",
                "Check R2 delete_object permission",
                {"key": key},
            )

    finally:
        try:
            os.unlink(tmp_path)
        except Exception:
            pass

    return passed({
        "bucket": s.storage.bucket_name,
        "key": key,
        "payload_bytes": len(payload),
        "head_latency_ms": health.get("latency_ms"),
    })


# ============================================================================
# Test 7: Channel CRUD via Railway API
# ============================================================================


async def test_07_channel_crud(railway_url: str | None) -> TestResult:
    """Direct DB CRUD via Supabase pooler URL (bypasses Railway)."""
    from src.config import get_settings

    s = get_settings()
    db_url = s.database.db_url
    if not db_url:
        return skip(
            "SUPABASE_DB_URL not set in backend/.env",
            "Set SUPABASE_DB_URL to the session pooler URL (port 6543)",
        )

    try:
        import psycopg
    except ImportError:
        return fail("psycopg not installed", "pip install 'psycopg[binary,pool]'")

    test_name = "__validation_test__"
    # The channels table has no `niche` column on this schema — record the
    # niche the user requested in the description field for traceability.
    description = "niche=financial_crime; production_validation"
    channel_id: str | None = None
    ops: list[str] = []

    try:
        # psycopg async API. Use a single connection for the whole flow so
        # any pgbouncer-style pooling stays consistent.
        async with await psycopg.AsyncConnection.connect(db_url) as conn:
            ops.append("CONNECT")

            # Pre-cleanup: remove any leftover __validation_test__ rows from
            # a prior interrupted run so the INSERT doesn't see duplicates.
            async with conn.cursor() as cur:
                await cur.execute(
                    "DELETE FROM channels WHERE name = %s", (test_name,)
                )

            # INSERT
            async with conn.cursor() as cur:
                await cur.execute(
                    "INSERT INTO channels (name, description) "
                    "VALUES (%s, %s) RETURNING id, name, description, status",
                    (test_name, description),
                )
                row = await cur.fetchone()
                if not row:
                    return fail("INSERT returned no row")
                channel_id = str(row[0])
                ops.append("INSERT")

            # SELECT
            async with conn.cursor() as cur:
                await cur.execute(
                    "SELECT id, name, description, status FROM channels WHERE id = %s",
                    (channel_id,),
                )
                got = await cur.fetchone()
                if not got:
                    return fail("SELECT returned no row after INSERT")
                if got[1] != test_name:
                    return fail(f"name mismatch: got {got[1]!r}, expected {test_name!r}")
                if got[2] != description:
                    return fail(f"description mismatch: got {got[2]!r}")
                ops.append("SELECT")

            # DELETE
            async with conn.cursor() as cur:
                await cur.execute(
                    "DELETE FROM channels WHERE id = %s", (channel_id,)
                )
                if cur.rowcount != 1:
                    return fail(f"DELETE affected {cur.rowcount} rows, expected 1")
                ops.append("DELETE")

            # Verify gone
            async with conn.cursor() as cur:
                await cur.execute(
                    "SELECT 1 FROM channels WHERE id = %s", (channel_id,)
                )
                if await cur.fetchone() is not None:
                    return fail("Row still present after DELETE")

            await conn.commit()
    except psycopg.OperationalError as exc:
        return fail(
            f"DB connection failed: {exc}",
            "Verify SUPABASE_DB_URL pooler URL (host=*.pooler.supabase.com, port=6543) is reachable",
        )
    except Exception as exc:
        # Best-effort cleanup on unexpected error
        if channel_id:
            try:
                async with await psycopg.AsyncConnection.connect(db_url) as conn2:
                    async with conn2.cursor() as cur:
                        await cur.execute(
                            "DELETE FROM channels WHERE id = %s", (channel_id,)
                        )
                    await conn2.commit()
            except Exception:
                pass
        return fail(f"CRUD flow failed: {type(exc).__name__}: {exc}")

    # Mask the password in the URL for the report
    import re

    masked_url = re.sub(r"://([^:]+):[^@]+@", r"://\1:***@", db_url)

    return passed({
        "ops": ops,
        "channel_id": channel_id,
        "name": test_name,
        "db_url": masked_url,
        "note": "channels table has no `niche` column; recorded as description",
    })


# ============================================================================
# Test 8: End-to-end pipeline trigger
# ============================================================================


async def test_08_e2e_pipeline(railway_url: str | None) -> TestResult:
    if not railway_url:
        return skip(
            "RAILWAY_URL not set",
            "Export RAILWAY_URL or pass --railway-url",
        )

    import httpx

    base = railway_url.rstrip("/")
    POLL_INTERVAL = 30
    MAX_POLL_MINUTES = 5

    # The current API only exposes `POST /api/v1/pipeline/trigger/{video_id}`,
    # which requires an existing video row. There is no public endpoint for
    # "create a video for niche=X with rhyo_report_path=Y" — that flow lives
    # in internal orchestration code. Per spec, SKIP if the niche-trigger
    # endpoint isn't wired up.

    async with httpx.AsyncClient(timeout=60.0, follow_redirects=True) as client:
        try:
            r = await client.post(
                f"{base}/api/v1/pipeline/trigger",
                json={
                    "channel_niche": "travel_safety",
                    "rhyo_report_path": "fixtures/rhyo_reports/hyderabad_banjara_hills.md",
                    "video_length_minutes": 15,
                    "source": "production_validation",
                },
            )
        except Exception as exc:
            return fail(
                f"POST /api/v1/pipeline/trigger failed: {exc}",
                "Network error; Railway not reachable",
            )

        if r.status_code in (404, 405):
            return skip(
                "POST /api/v1/pipeline/trigger (no video_id) not wired",
                "Only POST /api/v1/pipeline/trigger/{video_id} exists. There is no public "
                "endpoint that creates a video from a Rhyo fixture path; that requires "
                "internal orchestration. Add a niche-level trigger route to enable Test 8.",
            )

        if r.status_code not in (200, 201, 202):
            return fail(
                f"Pipeline trigger returned {r.status_code}",
                "Check that /api/v1/pipeline/trigger accepts this payload shape",
                {"status": r.status_code, "body": r.text[:500]},
            )

        try:
            body = r.json()
            video_id = body.get("video_id") or body.get("id") or body.get("job_id")
        except Exception:
            return fail(
                "Pipeline trigger response not JSON",
                None,
                {"body": r.text[:500]},
            )

        if not video_id:
            return fail(
                "Pipeline trigger response missing video_id/id/job_id",
                "Check pipeline trigger response schema",
                {"body": body},
            )

        # Poll
        stages_seen: set[str] = set()
        deadline = time.monotonic() + MAX_POLL_MINUTES * 60
        last_status: dict[str, Any] = {}

        while time.monotonic() < deadline:
            try:
                r = await client.get(f"{base}/api/v1/videos/{video_id}")
            except Exception as exc:
                log(f"    poll error: {exc}")
                await asyncio.sleep(POLL_INTERVAL)
                continue

            if r.status_code != 200:
                log(f"    poll returned {r.status_code}")
                await asyncio.sleep(POLL_INTERVAL)
                continue

            last_status = r.json()
            current_stage = last_status.get("status") or last_status.get("stage") or "unknown"
            stages_seen.add(current_stage)
            log(f"    [poll] stage={current_stage} elapsed={int(time.monotonic() - (deadline - MAX_POLL_MINUTES*60))}s")

            if current_stage in ("completed", "published", "failed", "error"):
                break

            await asyncio.sleep(POLL_INTERVAL)

        stages_required = {"script_generation", "image_generation"}
        stages_completed = last_status.get("stages_completed", []) or []
        completed_set = set(stages_completed) if isinstance(stages_completed, list) else set()

        if stages_required.issubset(completed_set):
            return passed({
                "video_id": video_id,
                "final_stage": last_status.get("status"),
                "stages_completed": list(completed_set),
                "stages_seen_during_poll": list(stages_seen),
            })

        return fail(
            f"Required stages not completed: missing={stages_required - completed_set}",
            "Check worker logs on Railway for per-stage errors",
            {
                "video_id": video_id,
                "final_status": last_status,
                "stages_seen": list(stages_seen),
            },
        )


# ============================================================================
# Markdown report
# ============================================================================


def write_markdown_report() -> Path:
    DOCS_DIR.mkdir(parents=True, exist_ok=True)
    out = DOCS_DIR / "PRODUCTION_VALIDATION_RESULTS.md"

    total = len(RESULTS)
    passed_ct = sum(1 for r in RESULTS if r.status == "PASS")
    failed_ct = sum(1 for r in RESULTS if r.status == "FAIL")
    skipped_ct = sum(1 for r in RESULTS if r.status == "SKIP")
    total_cost = sum((r.cost_usd for r in RESULTS), Decimal("0"))
    total_time = time.monotonic() - START_TIME

    lines: list[str] = [
        "# CrimeMill Production Validation Results",
        "",
        f"Generated: {time.strftime('%Y-%m-%d %H:%M:%S')}",
        "",
        "## Summary",
        "",
        f"- **Total tests:** {total}",
        f"- **Passed:** {passed_ct}",
        f"- **Failed:** {failed_ct}",
        f"- **Skipped:** {skipped_ct}",
        f"- **Total time:** {total_time/60:.1f} min ({total_time:.0f}s)",
        f"- **Total API cost:** ${total_cost}",
        "",
        "## Per-test results",
        "",
        "| # | Test | Status | Duration | Cost | Details |",
        "|---|---|---|---|---|---|",
    ]

    for r in RESULTS:
        status_badge = {"PASS": "PASS", "FAIL": "FAIL", "SKIP": "SKIP"}[r.status]
        detail_str = ""
        if r.status == "PASS" and r.details:
            detail_str = ", ".join(
                f"{k}={v}" for k, v in list(r.details.items())[:3] if not str(v).startswith("{")
            )[:200]
        elif r.status == "FAIL" and r.error:
            detail_str = r.error.splitlines()[0][:200]
        elif r.status == "SKIP":
            detail_str = r.details.get("reason", "")[:200]
        lines.append(
            f"| {r.test_id} | {r.name} | {status_badge} | {r.duration_s:.1f}s | ${r.cost_usd} | {detail_str} |"
        )

    lines.extend(["", "## Detailed output", ""])
    for r in RESULTS:
        lines.append(f"### Test {r.test_id}: {r.name}")
        lines.append("")
        lines.append(f"**Status:** {r.status}  ")
        lines.append(f"**Duration:** {r.duration_s:.1f}s  ")
        lines.append(f"**Cost:** ${r.cost_usd}")
        lines.append("")
        if r.details:
            lines.append("```json")
            try:
                lines.append(json.dumps(r.details, indent=2, default=str))
            except Exception:
                lines.append(str(r.details))
            lines.append("```")
        if r.error:
            lines.append("**Error:**")
            lines.append("```")
            lines.append(r.error[:2000])
            lines.append("```")
        if r.suggested_fix:
            lines.append(f"**Suggested fix:** {r.suggested_fix}")
        lines.append("")

    out.write_text("\n".join(lines), encoding="utf-8")
    return out


# ============================================================================
# Main
# ============================================================================


ALL_TESTS = {
    1: ("Railway /health", test_01_railway_health, True),
    2: ("Railway -> Supabase", test_02_railway_supabase, True),
    3: ("Remotion Lambda render", test_03_remotion_render, False),
    4: ("Street Level travel script", test_04_travel_script, False),
    5: ("CrimeMill crime script", test_05_crime_script, False),
    6: ("R2 round-trip", test_06_r2_round_trip, False),
    7: ("DB CRUD via pooler", test_07_channel_crud, True),
    8: ("E2E pipeline trigger", test_08_e2e_pipeline, True),
}


async def main() -> int:
    # Force UTF-8 on Windows consoles so non-ASCII characters in test names
    # or details don't crash the run with cp1252 UnicodeEncodeError.
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
        except Exception:
            pass

    parser = argparse.ArgumentParser()
    parser.add_argument("--only", help="Comma-separated test IDs (e.g. 4,5,6)")
    parser.add_argument("--skip", help="Comma-separated test IDs to skip")
    parser.add_argument("--railway-url", help="Railway service URL for tests 1,2,7,8")
    args = parser.parse_args()

    railway_url = get_railway_url(args.railway_url)

    if args.only:
        selected = set(int(x.strip()) for x in args.only.split(","))
    else:
        selected = set(ALL_TESTS.keys())
    if args.skip:
        selected -= set(int(x.strip()) for x in args.skip.split(","))

    log(f"Running tests: {sorted(selected)}")
    if railway_url:
        log(f"Railway URL: {railway_url}")
    else:
        log("Railway URL: (not set — Railway tests will skip)")

    for tid in sorted(selected):
        if tid not in ALL_TESTS:
            log(f"Unknown test id: {tid}")
            continue
        name, fn, needs_railway = ALL_TESTS[tid]
        if needs_railway:
            await run_test(tid, name, lambda f=fn: f(railway_url))  # type: ignore[misc]
        else:
            await run_test(tid, name, fn)

    report = write_markdown_report()
    log(f"Report written: {report}")

    passed_ct = sum(1 for r in RESULTS if r.status == "PASS")
    failed_ct = sum(1 for r in RESULTS if r.status == "FAIL")
    skipped_ct = sum(1 for r in RESULTS if r.status == "SKIP")
    total_cost = sum((r.cost_usd for r in RESULTS), Decimal("0"))
    elapsed = time.monotonic() - START_TIME

    print()
    print("=" * 60)
    print("PRODUCTION VALIDATION RESULTS")
    print("=" * 60)
    short_names = {
        1: "Railway health",
        2: "Railway DB",
        3: "Remotion Lambda render",
        4: "Street Level script",
        5: "CrimeMill script",
        6: "R2 round-trip",
        7: "DB CRUD",
        8: "Pipeline trigger",
    }
    for r in RESULTS:
        label = short_names.get(r.test_id, r.name)
        line_prefix = f"[{r.status}] Test {r.test_id}: {label} "
        leader = "." * max(2, 48 - len(line_prefix))
        cost_str = f" (${r.cost_usd})" if r.cost_usd > 0 else ""
        if r.status == "SKIP":
            reason = (r.details or {}).get("reason", "")
            print(f"{line_prefix}{leader} ({reason[:60]})")
        else:
            print(f"{line_prefix}{leader} {r.duration_s:5.1f}s{cost_str}")
    print("=" * 60)
    total = len(RESULTS)
    print(f"TOTAL: {passed_ct}/{total} passed, {failed_ct} failed, {skipped_ct} skipped")
    print(f"COST:  ${total_cost}")
    print(f"TIME:  {elapsed:.1f}s")
    print("=" * 60)

    return 0 if failed_ct == 0 else 1


if __name__ == "__main__":
    # psycopg's async API requires SelectorEventLoop on Windows. The default
    # is ProactorEventLoop, which raises InterfaceError. Switch the policy
    # before asyncio.run() spins up its loop.
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    sys.exit(asyncio.run(main()))
