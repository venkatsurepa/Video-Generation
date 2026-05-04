"""End-to-end smoke test for CrimeMill external dependencies.

Run from backend/ directory: python scripts/smoke_test.py
"""
# Dense one-line `if cond: append(...)` style is intentional — keeps the
# missing-var checklist scannable. Nested `with psycopg.connect(...) as
# conn: with conn.cursor() as cur:` is also kept for clarity.
# ruff: noqa: E701, SIM117
from __future__ import annotations

import sys
from pathlib import Path

# Ensure src is importable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.config import get_settings  # noqa: E402

RESULTS: list[tuple[str, bool, str]] = []

def record(name: str, ok: bool, detail: str = "") -> None:
    RESULTS.append((name, ok, detail))
    symbol = "PASS" if ok else "FAIL"
    print(f"[{symbol}] {name}" + (f" - {detail}" if detail else ""))


def test_config_loaded() -> None:
    try:
        s = get_settings()
        missing = []
        if not s.database.url: missing.append("SUPABASE_URL")
        if not s.database.anon_key: missing.append("SUPABASE_ANON_KEY")
        if not s.database.service_role_key: missing.append("SUPABASE_SERVICE_ROLE_KEY")
        if not s.database.db_url: missing.append("SUPABASE_DB_URL")
        if not s.anthropic.api_key: missing.append("ANTHROPIC_API_KEY")
        if not s.fish_audio.api_key: missing.append("FISH_AUDIO_API_KEY")
        if not s.fal.api_key: missing.append("FAL_AI_API_KEY")
        if not s.groq.api_key: missing.append("GROQ_API_KEY")
        if not s.storage.access_key_id: missing.append("R2_ACCESS_KEY_ID")
        if not s.storage.secret_access_key: missing.append("R2_SECRET_ACCESS_KEY")
        if not s.storage.endpoint_url: missing.append("R2_ENDPOINT_URL")
        if not s.remotion.aws_access_key_id: missing.append("REMOTION_AWS_ACCESS_KEY_ID")
        if not s.remotion.aws_secret_access_key: missing.append("REMOTION_AWS_SECRET_ACCESS_KEY")
        if missing:
            record("Config loaded", False, f"Missing: {', '.join(missing)}")
        else:
            record("Config loaded", True, "all required env vars present")
    except Exception as e:
        record("Config loaded", False, str(e))


def test_supabase_db() -> None:
    try:
        import psycopg
        s = get_settings()
        if "REPLACE_ME" in s.database.db_url:
            record("Supabase DB", False, "SUPABASE_DB_URL still contains REPLACE_ME placeholder")
            return
        with psycopg.connect(s.database.db_url, connect_timeout=10) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT COUNT(*) FROM pg_tables WHERE schemaname = 'public'")
                count = cur.fetchone()[0]
        record("Supabase DB", True, f"{count} tables in public schema")
    except Exception as e:
        record("Supabase DB", False, str(e)[:200])


def test_anthropic() -> None:
    try:
        from anthropic import Anthropic
        s = get_settings()
        client = Anthropic(api_key=s.anthropic.api_key)
        msg = client.messages.create(
            model="claude-haiku-4-5",
            max_tokens=50,
            messages=[{"role": "user", "content": "Say hi in 3 words"}],
        )
        text = msg.content[0].text if msg.content else ""
        record("Anthropic API", True, f"response: {text.strip()[:50]}")
    except Exception as e:
        record("Anthropic API", False, str(e)[:200])


def test_fish_audio() -> None:
    try:
        import httpx
        s = get_settings()
        r = httpx.get(
            "https://api.fish.audio/model",
            headers={"Authorization": f"Bearer {s.fish_audio.api_key}"},
            timeout=10,
        )
        if r.status_code == 200:
            record("Fish Audio API", True, f"HTTP {r.status_code}")
        else:
            record("Fish Audio API", False, f"HTTP {r.status_code}: {r.text[:150]}")
    except Exception as e:
        record("Fish Audio API", False, str(e)[:200])


def test_fal() -> None:
    try:
        import httpx
        s = get_settings()
        # Use a lightweight models endpoint instead of /health
        r = httpx.get(
            "https://queue.fal.run/",
            headers={"Authorization": f"Key {s.fal.api_key}"},
            timeout=10,
        )
        # 200, 401, 403, 404 all indicate the key was at least sent
        if r.status_code in (200, 404):
            record("fal.ai API", True, f"HTTP {r.status_code} (reachable)")
        elif r.status_code in (401, 403):
            record("fal.ai API", False, f"HTTP {r.status_code}: auth failed, key may be invalid")
        else:
            record("fal.ai API", False, f"HTTP {r.status_code}: {r.text[:150]}")
    except Exception as e:
        record("fal.ai API", False, str(e)[:200])


def test_groq() -> None:
    try:
        import httpx
        s = get_settings()
        r = httpx.get(
            "https://api.groq.com/openai/v1/models",
            headers={"Authorization": f"Bearer {s.groq.api_key}"},
            timeout=10,
        )
        if r.status_code == 200:
            data = r.json()
            count = len(data.get("data", []))
            record("Groq API", True, f"{count} models available")
        else:
            record("Groq API", False, f"HTTP {r.status_code}: {r.text[:150]}")
    except Exception as e:
        record("Groq API", False, str(e)[:200])


def test_r2() -> None:
    try:
        import boto3
        from botocore.config import Config
        s = get_settings()
        client = boto3.client(
            "s3",
            endpoint_url=s.storage.endpoint_url,
            aws_access_key_id=s.storage.access_key_id,
            aws_secret_access_key=s.storage.secret_access_key,
            region_name="auto",
            config=Config(signature_version="s3v4"),
        )
        response = client.list_objects_v2(Bucket=s.storage.bucket_name, MaxKeys=1)
        count = response.get("KeyCount", 0)
        # Also try a small write + delete to verify write perms
        test_key = "_smoke_test_delete_me.txt"
        client.put_object(Bucket=s.storage.bucket_name, Key=test_key, Body=b"smoke test")
        client.delete_object(Bucket=s.storage.bucket_name, Key=test_key)
        record("R2 Storage (R/W)", True, f"bucket accessible, {count} existing objects, write+delete works")
    except Exception as e:
        record("R2 Storage (R/W)", False, str(e)[:200])


def test_aws() -> None:
    try:
        import boto3
        s = get_settings()
        client = boto3.client(
            "sts",
            aws_access_key_id=s.remotion.aws_access_key_id,
            aws_secret_access_key=s.remotion.aws_secret_access_key,
            region_name=s.remotion.aws_region,
        )
        identity = client.get_caller_identity()
        account = identity["Account"]
        arn = identity["Arn"]
        record("AWS STS", True, f"account {account}, user {arn.split('/')[-1]}")
    except Exception as e:
        record("AWS STS", False, str(e)[:200])


def test_aws_lambda_perms() -> None:
    try:
        import boto3
        s = get_settings()
        client = boto3.client(
            "lambda",
            aws_access_key_id=s.remotion.aws_access_key_id,
            aws_secret_access_key=s.remotion.aws_secret_access_key,
            region_name=s.remotion.aws_region,
        )
        response = client.list_functions(MaxItems=1)
        fn_count = len(response.get("Functions", []))
        record("AWS Lambda perms", True, f"can list functions ({fn_count} existing)")
    except Exception as e:
        record("AWS Lambda perms", False, str(e)[:200])


def main() -> int:
    print("CrimeMill End-to-End Smoke Test")
    print("=" * 60)
    test_config_loaded()
    test_supabase_db()
    test_anthropic()
    test_fish_audio()
    test_fal()
    test_groq()
    test_r2()
    test_aws()
    test_aws_lambda_perms()
    print("=" * 60)
    passed = sum(1 for _, ok, _ in RESULTS if ok)
    total = len(RESULTS)
    print(f"RESULT: {passed}/{total} passed")
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
