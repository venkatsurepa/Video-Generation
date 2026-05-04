"""Travel-safety script generation handler.

Routed to from ``handle_script_generation`` when channel.niche == 'travel_safety'.
Runs the multi-call ``TravelSafetyScriptGenerator`` against a Rhyo intelligence
report and mirrors the artifact shape that the rest of the pipeline (scene
rendering, voiceover, thumbnails) expects.

The Rhyo report is sourced from a fixture path supplied in the payload
(``payload['rhyo_report_path']``) or as inline markdown
(``payload['rhyo_report_markdown']``). Inline markdown is staged to a temp
file because the generator's loader is path-based.
"""
from __future__ import annotations

import contextlib
import json
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

import structlog

from src.pipeline.handlers._helpers import _TMP_ROOT
from src.utils.cost_tracker import track_cost

if TYPE_CHECKING:
    import uuid

    from psycopg import AsyncConnection

    from src.pipeline.worker import PipelineWorker

logger = structlog.get_logger(__name__)


async def handle_travel_script_generation(
    worker: PipelineWorker,
    video_id: uuid.UUID,
    payload: dict[str, Any],
    video: dict[str, Any],
) -> dict[str, Any]:
    """Generate a travel-safety script from a Rhyo intelligence report."""
    from src.services.script_generators.travel_safety_generator import (
        TravelSafetyScriptGenerator,
    )

    assert worker._http is not None
    channel_id = video["channel_id"]
    topic_data = video.get("topic") or {}

    report_path, cleanup_tmp = _resolve_report_path(payload, topic_data)
    try:
        gen = TravelSafetyScriptGenerator(worker._settings, worker._http)
        artifacts: Any = await worker._circuits["anthropic"].call(
            gen.run, report_path
        )
    finally:
        if cleanup_tmp is not None:
            with contextlib.suppress(OSError):
                cleanup_tmp.unlink(missing_ok=True)

    word_count = len(artifacts.script_text.split())
    duration_seconds = sum(s.duration_seconds for s in artifacts.scenes) or max(
        60, int(word_count / 2.5)
    )

    # Persist artifacts in the same JSON shape the crime path uses, so
    # downstream stages (scene rendering, voiceover, thumbnails) don't need
    # to know which generator produced them.
    script_data = {
        "script_text": artifacts.script_text,
        "word_count": word_count,
        "estimated_duration_seconds": duration_seconds,
        "hook_type": "",  # multi-call pipeline doesn't surface a hook label
        "scenes": [
            {
                "scene_number": s.scene_id,
                "narration_text": s.narration,
                "scene_description": s.visual_description,
                "duration_seconds": s.duration_seconds,
            }
            for s in artifacts.scenes
        ],
        "image_prompts": [
            {"scene_number": p.scene_id, "prompt": p.prompt}
            for p in artifacts.image_prompts
        ],
        "titles": [{"title": artifacts.title, "formula": ""}],
        "description": artifacts.description,
        "destinations": [d.model_dump() for d in artifacts.destinations],
        "niche": "travel_safety",
        "format": artifacts.format,
        "include_sponsor_credit": artifacts.include_sponsor_credit,
    }
    script_path = _TMP_ROOT / f"{video_id}_script.json"
    script_path.write_text(json.dumps(script_data), encoding="utf-8")
    await worker._upload_to_r2(
        channel_id,
        video_id,
        "script.json",
        str(script_path),
        "application/json",
    )

    async with worker._pool.connection() as conn:
        await track_cost(
            cast("AsyncConnection[dict[str, object]]", conn),
            video_id,
            "script_generation",
            "anthropic",
            "claude",
            input_units=0,
            output_units=0,
            cost_usd=artifacts.total_cost_usd,
            latency_ms=0,
        )
        await _persist_destinations(conn, video_id, artifacts.destinations)
        from src.db.queries import UPDATE_VIDEO_FIELDS

        await conn.execute(
            UPDATE_VIDEO_FIELDS,
            {
                "video_id": video_id,
                "status": "script_generated",
                "title": artifacts.title,
                "description": artifacts.description,
                "script_word_count": word_count,
                "video_length_seconds": int(duration_seconds),
                "error_message": None,
            },
        )
        await conn.commit()

    return {
        "script_text": artifacts.script_text,
        "word_count": word_count,
        "duration_seconds": duration_seconds,
        "scene_count": len(artifacts.scenes),
        "image_prompt_count": len(artifacts.image_prompts),
        "title": artifacts.title,
        "description": artifacts.description,
        "destinations": [d.model_dump() for d in artifacts.destinations],
        "r2_script_key": worker._r2_key(channel_id, video_id, "script.json"),
        "cost_usd": str(artifacts.total_cost_usd),
        "niche": "travel_safety",
        "format": artifacts.format,
    }


def _resolve_report_path(
    payload: dict[str, Any], topic_data: dict[str, Any]
) -> tuple[Path, Path | None]:
    """Resolve a filesystem path to the Rhyo report markdown.

    Returns ``(path, cleanup_path)`` where cleanup_path is set when we
    materialised a temp file from inline markdown and the caller must
    delete it. Order of precedence:
      1. payload['rhyo_report_markdown']  — inline markdown (staged to tmp)
      2. payload['rhyo_report_path']      — path to a markdown file
      3. topic_data['rhyo_report_path']
    """
    inline_md = payload.get("rhyo_report_markdown")
    if isinstance(inline_md, str) and inline_md.strip():
        # NamedTemporaryFile(delete=False) is intentional — we hand the
        # path to the generator (which reopens it) and the caller deletes
        # via cleanup_tmp once the run completes.
        tmp = tempfile.NamedTemporaryFile(  # noqa: SIM115
            mode="w", suffix=".md", encoding="utf-8", delete=False
        )
        tmp.write(inline_md)
        tmp.close()
        return Path(tmp.name), Path(tmp.name)

    report_path = payload.get("rhyo_report_path") or topic_data.get("rhyo_report_path")
    if report_path:
        return Path(report_path), None

    raise RuntimeError(
        "travel_safety pipeline requires a Rhyo report. Provide either "
        "payload['rhyo_report_markdown'] or payload['rhyo_report_path']."
    )


async def _persist_destinations(
    conn: Any, video_id: uuid.UUID, destinations: list[Any]
) -> None:
    """Insert extracted destinations into video_destinations."""
    if not destinations:
        return
    async with conn.cursor() as cur:
        for d in destinations:
            await cur.execute(
                """
                INSERT INTO video_destinations
                  (video_id, country_code, region_or_state, city, poi_name,
                   relevance, safepath_tags)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT DO NOTHING
                """,
                (
                    video_id,
                    d.country_code,
                    d.region_or_state or None,
                    d.city,
                    d.poi_name or None,
                    d.relevance,
                    d.safepath_tags,
                ),
            )


__all__ = ["handle_travel_script_generation"]
