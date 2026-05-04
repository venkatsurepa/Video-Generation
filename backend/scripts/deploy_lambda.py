"""Deploy Remotion Lambda function and site, then print env values to paste.

Run from backend/ directory: python scripts/deploy_lambda.py

Does NOT modify .env — prints REMOTION_LAMBDA_FUNCTION_NAME and REMOTION_SERVE_URL
ready for manual copy.
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

VIDEO_DIR = Path(__file__).resolve().parent.parent.parent / "video"
REGION = "us-east-1"
SITE_NAME = "crimemill"


def run(cmd: list[str], cwd: Path) -> str:
    print(f"$ {' '.join(cmd)}  (cwd={cwd})")
    result = subprocess.run(
        cmd,
        cwd=str(cwd),
        capture_output=True,
        text=True,
        shell=False,
    )
    sys.stdout.write(result.stdout)
    sys.stderr.write(result.stderr)
    if result.returncode != 0:
        raise SystemExit(f"Command failed with exit {result.returncode}")
    return result.stdout + "\n" + result.stderr


def parse_function_name(output: str) -> str | None:
    # Remotion prints e.g. "Function name: remotion-render-4-0-180-mem2048mb-disk2048mb-300sec"
    for pat in (
        r"Function\s+name:\s*([A-Za-z0-9_\-]+)",
        r"functionName:\s*([A-Za-z0-9_\-]+)",
        r"(remotion-render-[A-Za-z0-9_\-]+)",
    ):
        m = re.search(pat, output)
        if m:
            return m.group(1)
    return None


def parse_serve_url(output: str) -> str | None:
    # Remotion prints e.g. "Serve URL: https://remotionlambda-xxxx.s3.us-east-1.amazonaws.com/sites/crimemill/index.html"
    for pat in (
        r"Serve\s*URL:\s*(https?://\S+)",
        r"serveUrl:\s*(https?://\S+)",
        r"(https?://remotionlambda-\S+/sites/[^\s\"']+)",
    ):
        m = re.search(pat, output)
        if m:
            return m.group(1).rstrip(".,;)")
    return None


def main() -> int:
    if not VIDEO_DIR.exists():
        print(f"video/ directory not found at {VIDEO_DIR}")
        return 1

    print("=" * 60)
    print("Step 1: Deploy Lambda function")
    print("=" * 60)
    fn_output = run(
        [
            "npx",
            "remotion",
            "lambda",
            "functions",
            "deploy",
            "--memory=2048",
            "--timeout=300",
            f"--region={REGION}",
        ],
        cwd=VIDEO_DIR,
    )
    function_name = parse_function_name(fn_output)

    print("=" * 60)
    print("Step 2: Deploy Lambda site")
    print("=" * 60)
    site_output = run(
        [
            "npx",
            "remotion",
            "lambda",
            "sites",
            "create",
            "src/index.ts",
            f"--region={REGION}",
            f"--site-name={SITE_NAME}",
        ],
        cwd=VIDEO_DIR,
    )
    serve_url = parse_serve_url(site_output)

    print()
    print("=" * 60)
    print("Add these to backend/.env:")
    print("=" * 60)
    print(f"REMOTION_LAMBDA_FUNCTION_NAME={function_name or '<PARSE_FAILED — check output above>'}")
    print(f"REMOTION_SERVE_URL={serve_url or '<PARSE_FAILED — check output above>'}")

    if not function_name or not serve_url:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
