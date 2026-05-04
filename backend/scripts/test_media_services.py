"""Independent media-service smoke tests (Fish Audio TTS, fal.ai Flux,
Groq Whisper). Each test calls the provider's HTTP API directly with
the key from backend/.env so they run independently of the Anthropic
credit balance.

Usage (from backend/):
    python scripts/test_media_services.py
"""
# Cross-platform tmp paths and direct HTTP calls keep the script free of
# the wider pipeline stack (pools, structlog, circuit breakers).
# ruff: noqa: SIM105

from __future__ import annotations

import asyncio
import sys
import tempfile
import time
import wave
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path
from typing import Any

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

TMP = Path(tempfile.gettempdir())
VOICEOVER_PATH = TMP / "test_voiceover.wav"
IMAGE_PATH = TMP / "test_image.png"

VOICE_TEXT = (
    "Welcome back to Street Level. Today we're breaking down the real "
    "safety data for one of the world's most visited cities."
)
IMAGE_PROMPT = (
    "Golden hour street photography of a busy Bangkok market, warm natural "
    "lighting, atmospheric, documentary travel photography, 16:9, photorealistic"
)


# ============================================================================
# Result framework
# ============================================================================


@dataclass
class TestResult:
    label: str
    status: str  # PASS | FAIL
    duration_s: float = 0.0
    cost_usd: Decimal = Decimal("0")
    details: dict[str, Any] = field(default_factory=dict)
    error: str | None = None


RESULTS: list[TestResult] = []
START = time.monotonic()


def log(msg: str) -> None:
    print(f"[{time.monotonic() - START:7.2f}s] {msg}", flush=True)


# ============================================================================
# Test A: Fish Audio TTS
# ============================================================================


async def test_a_fish_audio() -> TestResult:
    from src.config import get_settings

    label = "Test A: Fish Audio TTS"
    s = get_settings()
    if not s.fish_audio.api_key:
        return TestResult(label, "FAIL", error="FISH_AUDIO_API_KEY not set in backend/.env")

    import httpx

    # Mirror src/services/voiceover_generator.py constants.
    base_url = "https://api.fish.audio"
    endpoint = "/v1/tts"
    # Fish Audio currently caps WAV sample rate at 44100 (8000/16000/24000/
    # 32000/44100). The codebase's voiceover_generator.py:29 still hardcodes
    # 48000 — needs a follow-up fix.
    payload: dict[str, Any] = {
        "text": VOICE_TEXT,
        "format": "wav",
        "sample_rate": 44_100,
        # Omit reference_id → Fish uses the default speech-01-turbo voice.
    }
    headers = {"Authorization": f"Bearer {s.fish_audio.api_key}"}

    t0 = time.monotonic()
    try:
        async with httpx.AsyncClient(timeout=120.0) as http:
            try:
                with VOICEOVER_PATH.open("wb") as f:
                    async with http.stream(
                        "POST",
                        f"{base_url}{endpoint}",
                        json=payload,
                        headers=headers,
                    ) as response:
                        if response.status_code != 200:
                            body = await response.aread()
                            return TestResult(
                                label,
                                "FAIL",
                                duration_s=time.monotonic() - t0,
                                error=f"HTTP {response.status_code}: {body.decode('utf-8', errors='replace')[:300]}",
                            )
                        async for chunk in response.aiter_bytes(chunk_size=8192):
                            f.write(chunk)
            except httpx.HTTPError as exc:
                return TestResult(
                    label, "FAIL", duration_s=time.monotonic() - t0,
                    error=f"{type(exc).__name__}: {exc}",
                )
    except Exception as exc:
        return TestResult(
            label, "FAIL", duration_s=time.monotonic() - t0,
            error=f"{type(exc).__name__}: {exc}",
        )

    duration = time.monotonic() - t0
    size = VOICEOVER_PATH.stat().st_size

    if size <= 10_000:
        return TestResult(
            label, "FAIL", duration_s=duration,
            error=f"output is only {size} bytes (expected >10KB)",
            details={"path": str(VOICEOVER_PATH), "size_bytes": size},
        )

    # Read WAV duration
    audio_seconds: float = 0.0
    audio_format = "wav"
    try:
        with wave.open(str(VOICEOVER_PATH), "rb") as wav:
            frames = wav.getnframes()
            rate = wav.getframerate()
            audio_seconds = frames / float(rate) if rate else 0.0
            audio_format = f"wav {wav.getnchannels()}ch @ {rate}Hz"
    except wave.Error:
        # Not a strict WAV — Fish may have returned MP3 or chunked audio.
        # Header sniff fallback.
        first4 = VOICEOVER_PATH.read_bytes()[:4]
        if first4[:3] == b"ID3" or first4[:2] == b"\xff\xfb":
            audio_format = "mp3"
            # Approximate: assume Fish 32kbps mono → 4 KB/s
            audio_seconds = size / 4096

    if audio_seconds <= 5.0:
        return TestResult(
            label, "FAIL", duration_s=duration,
            error=f"audio is only {audio_seconds:.2f}s (expected >5s)",
            details={
                "path": str(VOICEOVER_PATH),
                "size_bytes": size,
                "format": audio_format,
                "audio_seconds": round(audio_seconds, 2),
            },
        )

    # Fish Audio Plus plan ≈ $0.0000647/char
    cost = (Decimal("0.0000647") * Decimal(len(VOICE_TEXT))).quantize(Decimal("0.000001"))

    return TestResult(
        label, "PASS", duration_s=duration, cost_usd=cost,
        details={
            "path": str(VOICEOVER_PATH),
            "size_bytes": size,
            "format": audio_format,
            "audio_seconds": round(audio_seconds, 2),
            "char_count": len(VOICE_TEXT),
        },
    )


# ============================================================================
# Test B: fal.ai Flux Dev
# ============================================================================


async def test_b_fal_image() -> TestResult:
    from src.config import get_settings

    label = "Test B: fal.ai Image"
    s = get_settings()
    if not s.fal.api_key:
        return TestResult(label, "FAIL", error="FAL_AI_API_KEY not set in backend/.env")

    import httpx

    # Mirror src/services/image_generator.py — sync URL with model in path.
    fal_model = "fal-ai/flux/dev"
    url = f"https://fal.run/{fal_model}"
    payload: dict[str, Any] = {
        "prompt": IMAGE_PROMPT,
        "image_size": {"width": 1280, "height": 720},  # 16:9
        "num_images": 1,
        "enable_safety_checker": False,
    }
    headers = {
        "Authorization": f"Key {s.fal.api_key}",
        "Content-Type": "application/json",
    }

    t0 = time.monotonic()
    try:
        async with httpx.AsyncClient(timeout=120.0) as http:
            resp = await http.post(url, json=payload, headers=headers)
            if resp.status_code != 200:
                return TestResult(
                    label, "FAIL", duration_s=time.monotonic() - t0,
                    error=f"HTTP {resp.status_code}: {resp.text[:300]}",
                )
            data = resp.json()
            images = data.get("images") or []
            if not images:
                return TestResult(
                    label, "FAIL", duration_s=time.monotonic() - t0,
                    error="fal.ai returned no images",
                    details={"response": data},
                )
            image_url = images[0].get("url")
            width = images[0].get("width")
            height = images[0].get("height")
            content_type = images[0].get("content_type", "")
            if not image_url:
                return TestResult(
                    label, "FAIL", duration_s=time.monotonic() - t0,
                    error="fal.ai response missing image URL",
                )

            # Download
            dl = await http.get(image_url, timeout=60.0)
            if dl.status_code != 200:
                return TestResult(
                    label, "FAIL", duration_s=time.monotonic() - t0,
                    error=f"image download HTTP {dl.status_code}",
                    details={"image_url": image_url},
                )
            IMAGE_PATH.write_bytes(dl.content)
    except Exception as exc:
        return TestResult(
            label, "FAIL", duration_s=time.monotonic() - t0,
            error=f"{type(exc).__name__}: {exc}",
        )

    duration = time.monotonic() - t0
    size = IMAGE_PATH.stat().st_size

    if size <= 50_000:
        return TestResult(
            label, "FAIL", duration_s=duration,
            error=f"image is only {size} bytes (expected >50KB)",
            details={"path": str(IMAGE_PATH), "size_bytes": size},
        )

    # Sniff PNG/JPEG/WEBP from magic bytes
    head = IMAGE_PATH.read_bytes()[:12]
    if head.startswith(b"\x89PNG"):
        fmt = "PNG"
    elif head.startswith(b"\xff\xd8\xff"):
        fmt = "JPEG"
    elif head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        fmt = "WEBP"
    else:
        fmt = content_type or "unknown"

    # fal.ai Flux Dev: ~$0.025 per megapixel ≈ $0.025 for 1280x720
    cost = Decimal("0.025")

    return TestResult(
        label, "PASS", duration_s=duration, cost_usd=cost,
        details={
            "path": str(IMAGE_PATH),
            "size_bytes": size,
            "format": fmt,
            "dimensions": f"{width}x{height}" if width and height else "unknown",
            "model": fal_model,
        },
    )


# ============================================================================
# Test C: Groq Whisper
# ============================================================================


async def test_c_groq_transcription(audio_path: Path | None) -> TestResult:
    from src.config import get_settings

    label = "Test C: Groq Transcription"
    s = get_settings()
    if not s.groq.api_key:
        return TestResult(label, "FAIL", error="GROQ_API_KEY not set in backend/.env")

    if not audio_path or not audio_path.exists():
        return TestResult(
            label, "FAIL",
            error=f"no input audio (Test A must pass first; expected {audio_path})",
        )

    import httpx

    url = "https://api.groq.com/openai/v1/audio/transcriptions"
    headers = {"Authorization": f"Bearer {s.groq.api_key}"}
    audio_bytes = audio_path.read_bytes()
    ext = audio_path.suffix.lower()
    mime = {".wav": "audio/wav", ".mp3": "audio/mpeg"}.get(ext, "audio/wav")

    t0 = time.monotonic()
    try:
        async with httpx.AsyncClient(timeout=120.0) as http:
            resp = await http.post(
                url,
                headers=headers,
                files={"file": (audio_path.name, audio_bytes, mime)},
                data={
                    "model": "whisper-large-v3-turbo",
                    "response_format": "verbose_json",
                    "language": "en",
                },
            )
            if resp.status_code != 200:
                return TestResult(
                    label, "FAIL", duration_s=time.monotonic() - t0,
                    error=f"HTTP {resp.status_code}: {resp.text[:300]}",
                )
            data = resp.json()
    except Exception as exc:
        return TestResult(
            label, "FAIL", duration_s=time.monotonic() - t0,
            error=f"{type(exc).__name__}: {exc}",
        )

    duration = time.monotonic() - t0
    transcript = (data.get("text") or "").strip()
    audio_seconds = float(data.get("duration") or 0.0)

    # Word-overlap check: at least 3 words from VOICE_TEXT must appear.
    src_words = {w.strip(".,!?;:").lower() for w in VOICE_TEXT.split() if len(w) > 2}
    out_words = {w.strip(".,!?;:").lower() for w in transcript.split() if len(w) > 2}
    overlap = src_words & out_words
    overlap_count = len(overlap)

    if overlap_count < 3:
        return TestResult(
            label, "FAIL", duration_s=duration,
            error=f"only {overlap_count} word(s) match the source text",
            details={"transcript": transcript[:300], "overlap": sorted(overlap)},
        )

    # Groq whisper-large-v3-turbo: $0.04/hour = $0.000667/min
    cost = (Decimal(str(audio_seconds)) / Decimal("60") * Decimal("0.000667")).quantize(
        Decimal("0.000001")
    )

    return TestResult(
        label, "PASS", duration_s=duration, cost_usd=cost,
        details={
            "transcript": transcript,
            "transcript_word_count": len(transcript.split()),
            "audio_seconds": round(audio_seconds, 2),
            "overlap_words": sorted(overlap)[:10],
            "latency_ms": int(duration * 1000),
        },
    )


# ============================================================================
# Main
# ============================================================================


async def main() -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
        except Exception:
            pass

    log("=== TEST A: Fish Audio TTS ===")
    a = await test_a_fish_audio()
    RESULTS.append(a)
    log(f"    [{a.status}] {a.label} ({a.duration_s:.1f}s, ${a.cost_usd})")
    if a.error:
        log(f"    error: {a.error[:200]}")
    if a.details:
        log(f"    details: {a.details}")

    log("=== TEST B: fal.ai Image ===")
    b = await test_b_fal_image()
    RESULTS.append(b)
    log(f"    [{b.status}] {b.label} ({b.duration_s:.1f}s, ${b.cost_usd})")
    if b.error:
        log(f"    error: {b.error[:200]}")
    if b.details:
        log(f"    details: {b.details}")

    log("=== TEST C: Groq Transcription ===")
    c = await test_c_groq_transcription(VOICEOVER_PATH if a.status == "PASS" else None)
    RESULTS.append(c)
    log(f"    [{c.status}] {c.label} ({c.duration_s:.1f}s, ${c.cost_usd})")
    if c.error:
        log(f"    error: {c.error[:200]}")
    if c.details:
        log(f"    details: {c.details}")

    # Summary
    print()
    print("=" * 60)
    print("MEDIA SERVICES TEST RESULTS")
    print("=" * 60)
    short = {
        "Test A: Fish Audio TTS": "Fish Audio TTS",
        "Test B: fal.ai Image": "fal.ai Image",
        "Test C: Groq Transcription": "Groq Transcription",
    }
    letters = ["A", "B", "C"]
    for letter, r in zip(letters, RESULTS, strict=False):
        name = short.get(r.label, r.label)
        prefix = f"[{r.status}] Test {letter}: {name} "
        leader = "." * max(2, 48 - len(prefix))
        cost_str = f" (${r.cost_usd})" if r.cost_usd > 0 else ""
        print(f"{prefix}{leader} {r.duration_s:5.1f}s{cost_str}")
    print("=" * 60)
    passed = sum(1 for r in RESULTS if r.status == "PASS")
    failed = sum(1 for r in RESULTS if r.status == "FAIL")
    total_cost = sum((r.cost_usd for r in RESULTS), Decimal("0"))
    elapsed = time.monotonic() - START
    print(f"TOTAL: {passed}/{len(RESULTS)} passed, {failed} failed")
    print(f"COST:  ${total_cost}")
    print(f"TIME:  {elapsed:.1f}s")
    print("=" * 60)
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    sys.exit(asyncio.run(main()))
