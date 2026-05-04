"""CrimeMill Admin CLI — primary interface for day-to-day operations.

Usage:
    python -m src.cli <command> [options]

All commands support ``--json`` for machine-readable output.
"""

from __future__ import annotations

import asyncio
import csv
import io
import uuid
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import click
import orjson
from rich import box
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

# ---------------------------------------------------------------------------
# Bootstrap: load .env from project root before importing app modules
# ---------------------------------------------------------------------------

_backend_dir = Path(__file__).resolve().parent.parent
_project_root = _backend_dir.parent
_env_file = _backend_dir / ".env"
if not _env_file.exists():
    _env_file = _project_root / ".env"

# ---------------------------------------------------------------------------
# Lazy imports — avoid import-time DB connections
# ---------------------------------------------------------------------------

console = Console()
err_console = Console(stderr=True)

# Global state for the async runtime
_pool = None
_settings = None
_http_client = None


def _json_serializer(obj: Any) -> Any:
    """Fallback serializer for orjson."""
    if isinstance(obj, (datetime, date)):
        return obj.isoformat()
    if isinstance(obj, Decimal):
        return float(obj)
    if isinstance(obj, uuid.UUID):
        return str(obj)
    raise TypeError(f"Cannot serialize {type(obj)}")


def _print_json(data: Any) -> None:
    """Print data as formatted JSON to stdout."""
    click.echo(orjson.dumps(data, default=_json_serializer, option=orjson.OPT_INDENT_2).decode())


def _run(coro: Any) -> Any:
    """Run an async coroutine in the event loop."""
    return asyncio.get_event_loop().run_until_complete(coro)


async def _ensure_pool() -> None:
    """Lazily initialize the DB pool and settings."""
    global _pool, _settings, _http_client
    if _pool is not None:
        return

    from src.config import get_settings
    from src.db.connection import create_pool

    _settings = get_settings()
    _pool = await create_pool(_settings.database.db_url, min_size=1, max_size=3)

    import httpx

    _http_client = httpx.AsyncClient(timeout=60.0)


async def _cleanup() -> None:
    """Close pool and HTTP client."""
    global _pool, _http_client
    if _http_client:
        await _http_client.aclose()
        _http_client = None
    if _pool:
        await _pool.close()
        _pool = None


def _get_pool() -> Any:
    return _pool


def _get_settings() -> Any:
    return _settings


def _get_http() -> Any:
    return _http_client


# ---------------------------------------------------------------------------
# Root CLI group
# ---------------------------------------------------------------------------


@click.group()
@click.option("--json", "json_output", is_flag=True, help="Output as JSON")
@click.pass_context
def cli(ctx: click.Context, json_output: bool) -> None:
    """CrimeMill Admin CLI — manage channels, pipelines, and analytics."""
    ctx.ensure_object(dict)
    ctx.obj["json"] = json_output

    # Set up async event loop
    try:
        loop = asyncio.get_event_loop()
        if loop.is_closed():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

    loop.run_until_complete(_ensure_pool())

    # Register cleanup
    ctx.call_on_close(lambda: asyncio.get_event_loop().run_until_complete(_cleanup()))


# ===================================================================
# CHANNEL commands
# ===================================================================


@cli.group()
def channel() -> None:
    """Manage channels."""


@channel.command("create")
@click.option("--name", required=True, help="Channel display name")
@click.option("--youtube-id", default="", help="YouTube channel ID (UC...)")
@click.option(
    "--niche",
    required=True,
    type=click.Choice(
        [
            "financial_crime",
            "travel_safety",
            "true_crime",
            "business_documentary",
            "educational",
            "other",
        ]
    ),
    help="Channel niche category (matches DB CHECK constraint)",
)
@click.option("--handle", default="", help="YouTube handle (e.g. fraud-files)")
@click.option("--description", default="", help="Channel description")
@click.option("--voice-id", default="", help="Fish Audio voice ID")
@click.option(
    "--thumbnail-archetype",
    default="mugshot_drama",
    type=click.Choice(
        [
            "mugshot_drama",
            "mystery_reveal",
            "crime_scene",
            "victim_memorial",
            "evidence_collage",
            "location_map",
        ]
    ),
)
@click.option(
    "--partner-app",
    default=None,
    type=click.Choice(["safepath", "none"]),
    help="Partner app association (e.g. safepath for travel_safety channels)",
)
@click.option(
    "--partner-app-url",
    default=None,
    help="Partner app website URL (e.g. https://safepath.travel)",
)
@click.option(
    "--partner-referral-code",
    default=None,
    help="Partner referral code for attribution",
)
@click.pass_context
def channel_create(
    ctx: click.Context,
    name: str,
    youtube_id: str,
    niche: str,
    handle: str,
    description: str,
    voice_id: str,
    thumbnail_archetype: str,
    partner_app: str | None,
    partner_app_url: str | None,
    partner_referral_code: str | None,
) -> None:
    """Create a new channel with default settings."""
    from src.models.channel import ChannelCreateInput
    from src.services.channel_manager import ChannelManager

    async def _create() -> None:
        mgr = ChannelManager(_get_settings(), _get_pool(), _get_http())
        inp = ChannelCreateInput(
            name=name,
            youtube_channel_id=youtube_id,
            handle=handle or name.lower().replace(" ", "-"),
            niche=niche,
            description=description,
            voice_id=voice_id,
            thumbnail_archetype=thumbnail_archetype,
            partner_app=partner_app,  # type: ignore[arg-type]
            partner_app_url=partner_app_url,
            partner_referral_code=partner_referral_code,
        )
        ch = await mgr.create_channel(inp)

        if ctx.obj["json"]:
            _print_json(
                {
                    "id": str(ch.id),
                    "name": ch.name,
                    "handle": ch.handle,
                    "status": ch.status,
                    "niche": niche,
                    "partner_app": partner_app,
                    "partner_app_url": partner_app_url,
                    "partner_referral_code": partner_referral_code,
                    "created_at": ch.created_at.isoformat(),
                }
            )
        else:
            partner_lines = ""
            if partner_app:
                partner_lines = (
                    f"\n  Partner: {partner_app}"
                    + (f" ({partner_app_url})" if partner_app_url else "")
                    + (
                        f"\n  Referral: {partner_referral_code}"
                        if partner_referral_code
                        else ""
                    )
                )
            console.print(
                Panel(
                    f"[bold green]Channel created successfully[/]\n\n"
                    f"  ID:     {ch.id}\n"
                    f"  Name:   {ch.name}\n"
                    f"  Handle: {ch.handle}\n"
                    f"  Niche:  {niche}\n"
                    f"  Status: {ch.status}{partner_lines}",
                    title="New Channel",
                    border_style="green",
                )
            )

    _run(_create())


@channel.command("list")
@click.pass_context
def channel_list(ctx: click.Context) -> None:
    """Show all channels with key stats."""
    from src.db import queries

    async def _list() -> None:
        async with _get_pool().connection() as conn:
            rows = await (await conn.execute(queries.LIST_CHANNELS_WITH_STATS)).fetchall()

        if ctx.obj["json"]:
            _print_json([dict(r) for r in rows])
            return

        if not rows:
            console.print("[dim]No channels found.[/]")
            return

        table = Table(title="Channels", box=box.ROUNDED, show_lines=True)
        table.add_column("Name", style="bold cyan", no_wrap=True)
        table.add_column("Handle", style="dim")
        table.add_column("Status", justify="center")
        table.add_column("Videos", justify="right")
        table.add_column("Published", justify="right")
        table.add_column("Total Cost", justify="right", style="yellow")
        table.add_column("ID", style="dim", no_wrap=True)

        for r in rows:
            status_color = {
                "active": "green",
                "paused": "yellow",
                "suspended": "red",
                "archived": "dim",
            }.get(r["status"], "white")
            table.add_row(
                r["name"],
                r["handle"] or "-",
                f"[{status_color}]{r['status']}[/]",
                str(r["total_videos"]),
                str(r["published_videos"]),
                f"${r['total_cost_usd']:.2f}",
                str(r["id"])[:8],
            )

        console.print(table)

    _run(_list())


@channel.command("setup-voice")
@click.option("--channel", "channel_name", required=True, help="Channel handle or name")
@click.option(
    "--sample-audio",
    required=True,
    type=click.Path(exists=True),
    help="Path to voice sample WAV file",
)
@click.pass_context
def channel_setup_voice(ctx: click.Context, channel_name: str, sample_audio: str) -> None:
    """Clone a voice from a sample audio file."""
    from src.services.channel_manager import ChannelManager

    async def _setup() -> None:
        mgr = ChannelManager(_get_settings(), _get_pool(), _get_http())
        channel_id = await mgr.resolve_channel_id(channel_name)
        if not channel_id:
            err_console.print(f"[red]Channel '{channel_name}' not found[/]")
            raise SystemExit(1)

        result = await mgr.clone_voice(channel_id, sample_audio)

        if ctx.obj["json"]:
            _print_json(result.model_dump())
        else:
            console.print(
                Panel(
                    f"[bold green]Voice cloned successfully[/]\n\n"
                    f"  Voice ID:   {result.voice_id}\n"
                    f"  Voice Name: {result.voice_name}\n"
                    f"  Sample:     {result.sample_audio_url}\n"
                    f"  Test:       {result.test_audio_url}",
                    title="Voice Clone",
                    border_style="green",
                )
            )

    _run(_setup())


@channel.command("setup-youtube-auth")
@click.option("--channel", "channel_name", required=True, help="Channel handle or name")
@click.pass_context
def channel_setup_youtube_auth(ctx: click.Context, channel_name: str) -> None:
    """Interactive OAuth flow for YouTube API authorization."""
    from src.services.channel_manager import ChannelManager

    async def _setup() -> None:
        mgr = ChannelManager(_get_settings(), _get_pool(), _get_http())
        channel_id = await mgr.resolve_channel_id(channel_name)
        if not channel_id:
            err_console.print(f"[red]Channel '{channel_name}' not found[/]")
            raise SystemExit(1)

        # Phase 1: generate auth URL and open browser
        initial = await mgr.setup_youtube_oauth(channel_id)

        if not initial.scopes:
            err_console.print(
                "[red]YouTube client_id/client_secret not configured. "
                "Set YOUTUBE_CLIENT_ID and YOUTUBE_CLIENT_SECRET in .env[/]"
            )
            raise SystemExit(1)

        console.print("\n[bold]YouTube OAuth Setup[/]")
        console.print("A browser window should have opened.")
        console.print("If not, visit the URL printed above and authorize the app.\n")

        auth_code = click.prompt("Paste the authorization code here")

        # Phase 2: exchange code for tokens
        result = await mgr.complete_oauth_exchange(channel_id, auth_code.strip())

        if ctx.obj["json"]:
            _print_json(result.model_dump())
        elif result.success:
            console.print(
                Panel(
                    f"[bold green]OAuth setup complete[/]\n\n"
                    f"  YouTube Channel: {result.youtube_channel_title}\n"
                    f"  Scopes: {', '.join(result.scopes)}",
                    title="YouTube Auth",
                    border_style="green",
                )
            )
        else:
            err_console.print(f"[red]OAuth setup failed: {result.youtube_channel_title}[/]")

    _run(_setup())


# ===================================================================
# PIPELINE commands
# ===================================================================


@cli.group()
def pipeline() -> None:
    """Manage video pipelines."""


@pipeline.command("trigger")
@click.option("--channel", "channel_name", required=True, help="Channel handle or name")
@click.option("--topic", required=True, help="Video topic/title")
@click.pass_context
def pipeline_trigger(ctx: click.Context, channel_name: str, topic: str) -> None:
    """Start a new video pipeline with the given topic."""
    from src.db import queries
    from src.pipeline.orchestrator import Orchestrator
    from src.services.channel_manager import ChannelManager

    async def _trigger() -> None:
        mgr = ChannelManager(_get_settings(), _get_pool(), _get_http())
        channel_id = await mgr.resolve_channel_id(channel_name)
        if not channel_id:
            err_console.print(f"[red]Channel '{channel_name}' not found[/]")
            raise SystemExit(1)

        async with _get_pool().connection() as conn:
            # Create video record
            row = await (
                await conn.execute(
                    queries.INSERT_VIDEO,
                    {
                        "channel_id": channel_id,
                        "title": topic,
                        "description": None,
                        "tags": [],
                        "topic": orjson.dumps({"title": topic}).decode(),
                    },
                )
            ).fetchone()
            assert row is not None
            video_id = row["id"]

            # Start pipeline (Orchestrator needs a connection, not pool)
            orch = Orchestrator(conn)
            stages = await orch.start_pipeline(
                video_id, {"title": topic, "channel_id": str(channel_id)}
            )

        if ctx.obj["json"]:
            _print_json(
                {
                    "video_id": str(video_id),
                    "channel_id": str(channel_id),
                    "topic": topic,
                    "enqueued_stages": stages,
                }
            )
        else:
            console.print(
                Panel(
                    f"[bold green]Pipeline started[/]\n\n"
                    f"  Video ID: {video_id}\n"
                    f"  Topic:    {topic}\n"
                    f"  Stages:   {', '.join(stages)}",
                    title="Pipeline Triggered",
                    border_style="green",
                )
            )

    _run(_trigger())


@pipeline.command("status")
@click.option("--video-id", required=True, help="Video UUID")
@click.pass_context
def pipeline_status(ctx: click.Context, video_id: str) -> None:
    """Show detailed pipeline status with timing and cost per stage."""
    from src.db import queries

    async def _status() -> None:
        vid = uuid.UUID(video_id)
        async with _get_pool().connection() as conn:
            # Get video info
            video_row = await (
                await conn.execute(queries.GET_VIDEO_STATUS, {"video_id": vid})
            ).fetchone()
            if not video_row:
                err_console.print(f"[red]Video {video_id} not found[/]")
                raise SystemExit(1)

            # Get pipeline jobs
            jobs = await (
                await conn.execute(queries.GET_PIPELINE_JOBS, {"video_id": vid})
            ).fetchall()

            # Get costs
            costs = await (
                await conn.execute(queries.GET_VIDEO_COST_SUMMARY, {"video_id": vid})
            ).fetchall()

        cost_by_stage: dict[str, Decimal] = {}
        for c in costs:
            stage = c["stage"]
            cost_by_stage[stage] = cost_by_stage.get(stage, Decimal("0")) + c["cost_usd"]

        if ctx.obj["json"]:
            _print_json(
                {
                    "video_id": video_id,
                    "title": video_row["title"],
                    "status": video_row["status"],
                    "jobs": [dict(j) for j in jobs],
                    "costs": [dict(c) for c in costs],
                }
            )
            return

        console.print(f"\n[bold]{video_row['title'] or 'Untitled'}[/]")
        console.print(f"Status: [bold]{video_row['status']}[/]  |  ID: {video_id}\n")

        table = Table(box=box.SIMPLE_HEAVY)
        table.add_column("Stage", style="cyan")
        table.add_column("Status", justify="center")
        table.add_column("Retries", justify="center")
        table.add_column("Cost", justify="right", style="yellow")
        table.add_column("Started", style="dim")
        table.add_column("Completed", style="dim")
        table.add_column("Error", style="red", max_width=40)

        status_icons = {
            "completed": "[green]done[/]",
            "in_progress": "[yellow]running[/]",
            "pending": "[dim]pending[/]",
            "failed": "[red]failed[/]",
            "dead_letter": "[bold red]dead[/]",
        }

        for j in jobs:
            stage_cost = cost_by_stage.get(j["stage"], Decimal("0"))
            table.add_row(
                j["stage"],
                status_icons.get(j["status"], j["status"]),
                f"{j['retry_count']}/{j['max_retries']}",
                f"${stage_cost:.4f}" if stage_cost else "-",
                j["started_at"].strftime("%H:%M:%S") if j.get("started_at") else "-",
                j["completed_at"].strftime("%H:%M:%S") if j.get("completed_at") else "-",
                (j["error_message"] or "")[:40] if j.get("error_message") else "",
            )

        console.print(table)
        total_cost = sum(cost_by_stage.values(), Decimal("0"))
        console.print(f"\n  Total cost: [bold yellow]${total_cost:.4f}[/]")

    _run(_status())


@pipeline.command("retry")
@click.option("--video-id", required=True, help="Video UUID")
@click.pass_context
def pipeline_retry(ctx: click.Context, video_id: str) -> None:
    """Retry all dead-letter jobs for a video."""
    from src.db import queries

    async def _retry() -> None:
        vid = uuid.UUID(video_id)
        async with _get_pool().connection() as conn:
            rows = await (
                await conn.execute(queries.RETRY_FAILED_JOBS, {"video_id": vid})
            ).fetchall()

        retried = [r["stage"] for r in rows]

        if ctx.obj["json"]:
            _print_json({"video_id": video_id, "retried_stages": retried})
        elif retried:
            console.print(f"[green]Retried {len(retried)} jobs:[/] {', '.join(retried)}")
        else:
            console.print("[dim]No failed/dead-letter jobs to retry.[/]")

    _run(_retry())


@pipeline.command("list")
@click.option("--status", "status_filter", default=None, help="Filter by video status")
@click.option("--channel", "channel_name", default=None, help="Filter by channel")
@click.option("--limit", default=20, help="Max results")
@click.pass_context
def pipeline_list(
    ctx: click.Context, status_filter: str | None, channel_name: str | None, limit: int
) -> None:
    """List videos filtered by status and channel."""
    from src.db import queries
    from src.services.channel_manager import ChannelManager

    async def _list() -> None:
        channel_id = None
        if channel_name:
            mgr = ChannelManager(_get_settings(), _get_pool(), _get_http())
            channel_id = await mgr.resolve_channel_id(channel_name)
            if not channel_id:
                err_console.print(f"[red]Channel '{channel_name}' not found[/]")
                raise SystemExit(1)

        async with _get_pool().connection() as conn:
            rows = await (
                await conn.execute(
                    queries.LIST_VIDEOS_FILTERED,
                    {
                        "status_filter": status_filter,
                        "channel_filter": channel_id,
                        "date_from": None,
                        "date_to": None,
                        "limit": limit,
                        "offset": 0,
                    },
                )
            ).fetchall()

        if ctx.obj["json"]:
            _print_json([dict(r) for r in rows])
            return

        if not rows:
            console.print("[dim]No videos found.[/]")
            return

        table = Table(title="Videos", box=box.ROUNDED)
        table.add_column("Title", style="cyan", max_width=50)
        table.add_column("Status", justify="center")
        table.add_column("Created", style="dim")
        table.add_column("ID", style="dim", no_wrap=True)

        status_colors = {
            "published": "green",
            "assembled": "blue",
            "failed": "red",
            "cancelled": "dim",
            "pending": "yellow",
        }

        for r in rows:
            color = status_colors.get(r["status"], "white")
            table.add_row(
                (r["title"] or "Untitled")[:50],
                f"[{color}]{r['status']}[/]",
                r["created_at"].strftime("%Y-%m-%d %H:%M") if r.get("created_at") else "-",
                str(r["id"])[:8],
            )

        console.print(table)

    _run(_list())


# ===================================================================
# REVIEW commands
# ===================================================================


@cli.group()
def review() -> None:
    """Review assembled videos."""


@review.command("queue")
@click.pass_context
def review_queue(ctx: click.Context) -> None:
    """Show all videos awaiting human review (assembled status)."""
    from src.db import queries

    async def _queue() -> None:
        async with _get_pool().connection() as conn:
            rows = await (await conn.execute(queries.LIST_REVIEW_QUEUE)).fetchall()

        if ctx.obj["json"]:
            _print_json([dict(r) for r in rows])
            return

        if not rows:
            console.print("[dim]No videos in review queue.[/]")
            return

        table = Table(title="Review Queue", box=box.ROUNDED, show_lines=True)
        table.add_column("#", style="dim", justify="right")
        table.add_column("Title", style="bold cyan", max_width=50)
        table.add_column("Channel", style="magenta")
        table.add_column("Created", style="dim")
        table.add_column("Video ID", style="dim", no_wrap=True)

        for i, r in enumerate(rows, 1):
            table.add_row(
                str(i),
                (r["title"] or "Untitled")[:50],
                r["channel_name"],
                r["created_at"].strftime("%Y-%m-%d %H:%M") if r.get("created_at") else "-",
                str(r["id"])[:8],
            )

        console.print(table)
        console.print(f"\n  [bold]{len(rows)}[/] video(s) awaiting review")

    _run(_queue())


@review.command("approve")
@click.option("--video-id", required=True, help="Video UUID")
@click.option("--notes", default="Approved", help="Approval notes")
@click.pass_context
def review_approve(ctx: click.Context, video_id: str, notes: str) -> None:
    """Approve video for scheduling and upload."""
    from src.db import queries

    async def _approve() -> None:
        vid = uuid.UUID(video_id)
        async with _get_pool().connection() as conn:
            row = await (
                await conn.execute(
                    queries.UPDATE_VIDEO_REVIEW,
                    {"video_id": vid, "status": "uploading", "notes": notes},
                )
            ).fetchone()

        if ctx.obj["json"]:
            _print_json({"video_id": video_id, "status": "uploading", "notes": notes})
        elif row:
            console.print(f"[green]Video {video_id[:8]} approved for upload[/]")
        else:
            err_console.print(f"[red]Video {video_id} not found[/]")

    _run(_approve())


@review.command("reject")
@click.option("--video-id", required=True, help="Video UUID")
@click.option("--reason", required=True, help="Rejection reason")
@click.pass_context
def review_reject(ctx: click.Context, video_id: str, reason: str) -> None:
    """Reject video with feedback."""
    from src.db import queries

    async def _reject() -> None:
        vid = uuid.UUID(video_id)
        async with _get_pool().connection() as conn:
            row = await (
                await conn.execute(
                    queries.UPDATE_VIDEO_REVIEW,
                    {"video_id": vid, "status": "failed", "notes": reason},
                )
            ).fetchone()

        if ctx.obj["json"]:
            _print_json({"video_id": video_id, "status": "failed", "reason": reason})
        elif row:
            console.print(f"[yellow]Video {video_id[:8]} rejected:[/] {reason}")
        else:
            err_console.print(f"[red]Video {video_id} not found[/]")

    _run(_reject())


# ===================================================================
# SCHEDULE commands
# ===================================================================


@cli.group()
def schedule() -> None:
    """Manage publishing schedule."""


@schedule.command("show")
@click.option("--days", default=14, help="Number of days to show")
@click.pass_context
def schedule_show(ctx: click.Context, days: int) -> None:
    """Show publishing calendar for the next N days."""
    from src.db import queries

    async def _show() -> None:
        async with _get_pool().connection() as conn:
            rows = await (
                await conn.execute(queries.LIST_SCHEDULED_VIDEOS, {"days": days})
            ).fetchall()

        if ctx.obj["json"]:
            _print_json([dict(r) for r in rows])
            return

        if not rows:
            console.print(f"[dim]No videos scheduled in the next {days} days.[/]")
            return

        table = Table(title=f"Publishing Calendar (next {days} days)", box=box.ROUNDED)
        table.add_column("Date", style="bold")
        table.add_column("Title", style="cyan", max_width=50)
        table.add_column("Channel", style="magenta")
        table.add_column("Status", justify="center")
        table.add_column("Video ID", style="dim", no_wrap=True)

        for r in rows:
            pub_date = (
                r["published_at"].strftime("%Y-%m-%d %H:%M")
                if r.get("published_at")
                else "Unscheduled"
            )
            table.add_row(
                pub_date,
                (r["title"] or "Untitled")[:50],
                r["channel_name"],
                r["status"],
                str(r["id"])[:8],
            )

        console.print(table)

    _run(_show())


@schedule.command("publish-now")
@click.option("--video-id", required=True, help="Video UUID")
@click.pass_context
def schedule_publish_now(ctx: click.Context, video_id: str) -> None:
    """Override schedule and publish immediately."""
    from src.db import queries

    async def _publish() -> None:
        vid = uuid.UUID(video_id)
        async with _get_pool().connection() as conn:
            row = await (
                await conn.execute(
                    queries.UPDATE_VIDEO_REVIEW,
                    {"video_id": vid, "status": "uploading", "notes": "Manual publish-now"},
                )
            ).fetchone()

        if ctx.obj["json"]:
            _print_json({"video_id": video_id, "status": "uploading"})
        elif row:
            console.print(f"[green]Video {video_id[:8]} queued for immediate upload[/]")
        else:
            err_console.print(f"[red]Video {video_id} not found[/]")

    _run(_publish())


# ===================================================================
# ANALYTICS commands
# ===================================================================


@cli.group()
def analytics() -> None:
    """View analytics and performance data."""


@analytics.command("daily")
@click.option("--channel", "channel_name", required=True, help="Channel handle or name")
@click.pass_context
def analytics_daily(ctx: click.Context, channel_name: str) -> None:
    """Show today's analytics for a channel."""
    from src.db import queries
    from src.services.channel_manager import ChannelManager

    async def _daily() -> None:
        mgr = ChannelManager(_get_settings(), _get_pool(), _get_http())
        channel_id = await mgr.resolve_channel_id(channel_name)
        if not channel_id:
            err_console.print(f"[red]Channel '{channel_name}' not found[/]")
            raise SystemExit(1)

        today = date.today()
        async with _get_pool().connection() as conn:
            row = await (
                await conn.execute(
                    queries.GET_CHANNEL_DAILY_ANALYTICS,
                    {"channel_id": channel_id, "metric_date": today},
                )
            ).fetchone()

        if ctx.obj["json"]:
            _print_json(dict(row) if row else {})
            return

        if not row or not row.get("total_views"):
            console.print(f"[dim]No analytics data for {today}.[/]")
            return

        console.print(
            Panel(
                f"  Views:        [bold]{row['total_views']:,}[/]\n"
                f"  Revenue:      [bold yellow]${row['total_revenue']:.2f}[/]\n"
                f"  CTR:          [bold]{float(row['avg_ctr']) * 100:.2f}%[/]\n"
                f"  Net Subs:     [bold]{row['net_subscribers']:+,}[/]\n"
                f"  Likes:        {row['total_likes']:,}\n"
                f"  Comments:     {row['total_comments']:,}",
                title=f"Daily Analytics — {today}",
                border_style="blue",
            )
        )

    _run(_daily())


@analytics.command("top-videos")
@click.option("--channel", "channel_name", required=True, help="Channel handle or name")
@click.option("--days", default=30, help="Time window in days")
@click.option(
    "--sort",
    "sort_by",
    default="revenue",
    type=click.Choice(["revenue", "views", "ctr", "watch_minutes"]),
)
@click.option("--limit", default=10, help="Number of results")
@click.pass_context
def analytics_top_videos(
    ctx: click.Context,
    channel_name: str,
    days: int,
    sort_by: str,
    limit: int,
) -> None:
    """Top performing videos by various metrics."""
    from src.db import queries
    from src.services.channel_manager import ChannelManager

    sort_map = {
        "revenue": "total_revenue",
        "views": "total_views",
        "ctr": "avg_ctr",
        "watch_minutes": "total_watch_minutes",
    }

    async def _top() -> None:
        mgr = ChannelManager(_get_settings(), _get_pool(), _get_http())
        channel_id = await mgr.resolve_channel_id(channel_name)
        if not channel_id:
            err_console.print(f"[red]Channel '{channel_name}' not found[/]")
            raise SystemExit(1)

        # Build query with safe column name substitution
        sort_column = sort_map[sort_by]
        query = queries.GET_TOP_VIDEOS.replace("{sort_column}", sort_column)

        async with _get_pool().connection() as conn:
            rows = await (
                await conn.execute(
                    query,
                    {"channel_id": channel_id, "days": days, "limit": limit},
                )
            ).fetchall()

        if ctx.obj["json"]:
            _print_json([dict(r) for r in rows])
            return

        if not rows:
            console.print(f"[dim]No video data in the last {days} days.[/]")
            return

        table = Table(title=f"Top Videos (last {days} days, by {sort_by})", box=box.ROUNDED)
        table.add_column("#", style="dim", justify="right")
        table.add_column("Title", style="cyan", max_width=45)
        table.add_column("Views", justify="right")
        table.add_column("Revenue", justify="right", style="yellow")
        table.add_column("CTR", justify="right")
        table.add_column("Watch Min", justify="right")

        for i, r in enumerate(rows, 1):
            table.add_row(
                str(i),
                (r["title"] or "Untitled")[:45],
                f"{r['total_views']:,}",
                f"${r['total_revenue']:.2f}",
                f"{float(r['avg_ctr']) * 100:.2f}%",
                f"{r['total_watch_minutes']:,.0f}",
            )

        console.print(table)

    _run(_top())


@analytics.command("costs")
@click.option("--days", default=30, help="Time window in days")
@click.pass_context
def analytics_costs(ctx: click.Context, days: int) -> None:
    """Cost summary: total spend, per-video average, by stage, by provider."""
    from src.db import queries

    async def _costs() -> None:
        async with _get_pool().connection() as conn:
            summary = await (
                await conn.execute(queries.GET_COST_SUMMARY, {"days": days})
            ).fetchone()

            providers = await (
                await conn.execute(queries.GET_COST_BY_PROVIDER, {"days": days})
            ).fetchall()

        if ctx.obj["json"]:
            _print_json(
                {
                    "summary": dict(summary) if summary else {},
                    "by_provider": [dict(p) for p in providers],
                }
            )
            return

        if not summary or not summary.get("total_cost"):
            console.print(f"[dim]No cost data in the last {days} days.[/]")
            return

        # Summary panel
        console.print(
            Panel(
                f"  Total videos:     [bold]{summary['total_videos']}[/]\n"
                f"  Total spend:      [bold yellow]${summary['total_cost']:.2f}[/]\n"
                f"  Avg per video:    [bold]${summary['avg_per_video']:.2f}[/]\n"
                f"\n  [bold]By Stage:[/]\n"
                f"    Script:         ${summary['script_cost'] or 0:.4f}\n"
                f"    Voiceover:      ${summary['voiceover_cost'] or 0:.4f}\n"
                f"    Images:         ${summary['image_cost'] or 0:.4f}\n"
                f"    Assembly:       ${summary['assembly_cost'] or 0:.4f}\n"
                f"    Thumbnails:     ${summary['thumbnail_cost'] or 0:.4f}\n"
                f"    Captions:       ${summary['caption_cost'] or 0:.4f}",
                title=f"Cost Summary (last {days} days)",
                border_style="yellow",
            )
        )

        # Provider table
        if providers:
            table = Table(title="By Provider", box=box.SIMPLE)
            table.add_column("Provider", style="cyan")
            table.add_column("Model", style="dim")
            table.add_column("Calls", justify="right")
            table.add_column("Total Cost", justify="right", style="yellow")

            for p in providers:
                table.add_row(
                    p["provider"],
                    p["model"],
                    str(p["calls"]),
                    f"${p['total_cost']:.4f}",
                )

            console.print(table)

    _run(_costs())


# ===================================================================
# TOPICS commands
# ===================================================================


@cli.group()
def topics() -> None:
    """Discover and manage video topics."""


@topics.command("discover")
@click.pass_context
def topics_discover(ctx: click.Context) -> None:
    """Run topic discovery pipeline and show top 20 scored topics."""
    from src.db import queries

    async def _discover() -> None:
        # Trigger discovery via the API's topic selector
        # For CLI, we just show existing discovered topics ranked by score
        async with _get_pool().connection() as conn:
            rows = await (
                await conn.execute(
                    queries.LIST_TOPICS_BY_PRIORITY,
                    {"priority_filter": None, "limit": 20},
                )
            ).fetchall()

        if ctx.obj["json"]:
            _print_json([dict(r) for r in rows])
            return

        if not rows:
            console.print("[dim]No discovered topics. Run topic discovery via the API first.[/]")
            return

        table = Table(title="Top Discovered Topics", box=box.ROUNDED, show_lines=True)
        table.add_column("#", style="dim", justify="right")
        table.add_column("Title", style="bold cyan", max_width=50)
        table.add_column("Category", style="magenta")
        table.add_column("Score", justify="right", style="yellow")
        table.add_column("Priority", justify="center")
        table.add_column("Saturation", justify="right")

        priority_colors = {
            "immediate": "bold red",
            "this_week": "yellow",
            "low": "dim",
            "archived": "dim",
        }

        for i, r in enumerate(rows, 1):
            pcolor = priority_colors.get(r["priority"], "white")
            table.add_row(
                str(i),
                (r["title"] or "")[:50],
                r["category"],
                f"{r['composite_score']:.1f}" if r.get("composite_score") else "-",
                f"[{pcolor}]{r['priority']}[/]",
                f"{r['competitor_saturation']:.0%}" if r.get("competitor_saturation") else "-",
            )

        console.print(table)

    _run(_discover())


@topics.command("list")
@click.option("--priority", default=None, help="Filter by priority level")
@click.option("--limit", default=50, help="Max results")
@click.pass_context
def topics_list(ctx: click.Context, priority: str | None, limit: int) -> None:
    """List discovered topics by priority."""
    from src.db import queries

    async def _list() -> None:
        async with _get_pool().connection() as conn:
            rows = await (
                await conn.execute(
                    queries.LIST_TOPICS_BY_PRIORITY,
                    {"priority_filter": priority, "limit": limit},
                )
            ).fetchall()

        if ctx.obj["json"]:
            _print_json([dict(r) for r in rows])
            return

        if not rows:
            console.print("[dim]No topics found.[/]")
            return

        table = Table(title="Topics", box=box.ROUNDED)
        table.add_column("Title", style="cyan", max_width=50)
        table.add_column("Category")
        table.add_column("Score", justify="right", style="yellow")
        table.add_column("Priority", justify="center")

        for r in rows:
            table.add_row(
                (r["title"] or "")[:50],
                r["category"],
                f"{r['composite_score']:.1f}" if r.get("composite_score") else "-",
                r["priority"],
            )

        console.print(table)

    _run(_list())


# ===================================================================
# HEALTH command
# ===================================================================


@cli.command("health")
@click.pass_context
def health_check(ctx: click.Context) -> None:
    """Run comprehensive health check."""
    from src.db import queries

    async def _health() -> None:
        results: dict[str, Any] = {}

        # 1. DB connectivity
        try:
            async with _get_pool().connection() as conn:
                await (await conn.execute("SELECT 1")).fetchone()
            results["database"] = {"status": "ok"}
        except Exception as e:
            results["database"] = {"status": "error", "error": str(e)}

        # 2. API key checks
        settings = _get_settings()
        api_keys = {
            "anthropic": bool(settings.anthropic.api_key),
            "fish_audio": bool(settings.fish_audio.api_key),
            "fal_ai": bool(settings.fal.api_key),
            "groq": bool(settings.groq.api_key),
            "youtube_oauth": bool(settings.youtube.client_id and settings.youtube.client_secret),
        }
        results["api_keys"] = api_keys

        # 3. R2 connectivity
        r2_configured = bool(
            settings.storage.account_id
            and settings.storage.access_key_id
            and settings.storage.secret_access_key
        )
        results["r2_storage"] = {"configured": r2_configured}

        # 4. Queue depth
        try:
            async with _get_pool().connection() as conn:
                queue_rows = await (await conn.execute(queries.GET_QUEUE_DEPTH)).fetchall()
                dead_row = await (await conn.execute(queries.GET_DEAD_LETTER_COUNT)).fetchone()
            results["queue"] = {
                "stages": [dict(r) for r in queue_rows],
                "total_dead_letter": dead_row["count"] if dead_row else 0,
            }
        except Exception as e:
            results["queue"] = {"status": "error", "error": str(e)}

        # 5. Channel health
        try:
            async with _get_pool().connection() as conn:
                channels = await (
                    await conn.execute(queries.LIST_CHANNELS, {"limit": 100, "offset": 0})
                ).fetchall()
            results["channels"] = {"count": len(channels)}
        except Exception as e:
            results["channels"] = {"status": "error", "error": str(e)}

        if ctx.obj["json"]:
            _print_json(results)
            return

        # Pretty print
        console.print("\n[bold]System Health Check[/]\n")

        # DB
        db_status = results["database"]["status"]
        if db_status == "ok":
            db_icon = "[green]OK[/]"
        else:
            db_icon = f"[red]ERROR: {results['database'].get('error', '')}[/]"
        console.print(f"  Database:       {db_icon}")

        # API keys
        for key, configured in api_keys.items():
            icon = "[green]configured[/]" if configured else "[red]missing[/]"
            console.print(f"  {key:16s} {icon}")

        # R2
        r2_icon = "[green]configured[/]" if r2_configured else "[red]not configured[/]"
        console.print(f"  R2 Storage:     {r2_icon}")

        # Queue
        if "stages" in results.get("queue", {}):
            dead = results["queue"]["total_dead_letter"]
            dead_icon = f"[red]{dead} dead-letter jobs[/]" if dead > 0 else "[green]clean[/]"
            console.print(f"  Queue:          {dead_icon}")
        else:
            console.print("  Queue:          [red]error[/]")

        # Channels
        if "count" in results.get("channels", {}):
            console.print(f"  Channels:       [bold]{results['channels']['count']}[/] registered")

        console.print()

    _run(_health())


# ===================================================================
# MUSIC commands
# ===================================================================


@cli.group()
def music() -> None:
    """Manage curated music library."""


@music.command("library")
@click.option("--status", "show_status", is_flag=True, default=True, help="Show library status")
@click.pass_context
def music_library(ctx: click.Context, show_status: bool) -> None:
    """Show music library status: tracks per mood, total duration."""
    from src.services.music_selector import MusicSelector

    async def _status() -> None:
        selector = MusicSelector(_get_settings(), _get_http())
        status = selector.get_library_status()

        if ctx.obj["json"]:
            _print_json(status.model_dump())
            return

        console.print(
            Panel(
                f"  Total tracks:     [bold]{status.total_tracks}[/]\n"
                f"  Total duration:   [bold]{status.total_duration_minutes:.1f} min[/]\n"
                f"\n  [bold]Tracks per mood:[/]",
                title="Music Library",
                border_style="cyan",
            )
        )

        for mood, count in sorted(status.tracks_per_mood.items()):
            bar = "#" * count
            console.print(f"    {mood:30s} {count:3d}  {bar}")

    _run(_status())


@music.command("add")
@click.option(
    "--file", "file_path", required=True, type=click.Path(exists=True), help="Path to audio file"
)
@click.option("--mood", required=True, help="Mood category")
@click.option("--title", required=True, help="Track title")
@click.option("--bpm", required=True, type=int, help="Beats per minute")
@click.option("--artist", default="Unknown", help="Artist name")
@click.pass_context
def music_add(
    ctx: click.Context,
    file_path: str,
    mood: str,
    title: str,
    bpm: int,
    artist: str,
) -> None:
    """Add a track to the curated music library."""
    import json
    import shutil

    library_path = Path(__file__).resolve().parent.parent / "assets" / "music" / "library.json"
    music_dir = library_path.parent / mood

    # Ensure mood directory exists
    music_dir.mkdir(parents=True, exist_ok=True)

    # Copy file to library
    dest = music_dir / Path(file_path).name
    if not dest.exists():
        shutil.copy2(file_path, dest)

    # Get duration via pydub
    try:
        from pydub import AudioSegment

        audio = AudioSegment.from_file(str(dest))
        duration = len(audio) / 1000.0
    except Exception:
        duration = 0.0

    # Update library.json
    track_id = f"{mood}_{title.lower().replace(' ', '_')}_{bpm}"
    new_track = {
        "id": track_id,
        "title": title,
        "artist": artist,
        "source": "custom",
        "mood_category": mood,
        "bpm": bpm,
        "duration_seconds": round(duration, 1),
        "file_path": f"{mood}/{Path(file_path).name}",
        "content_id_safe": True,
    }

    lib = json.loads(library_path.read_text()) if library_path.exists() else {"tracks": []}

    lib["tracks"].append(new_track)
    library_path.write_text(json.dumps(lib, indent=2))

    if ctx.obj["json"]:
        _print_json(new_track)
    else:
        console.print(f"[green]Added '{title}' ({mood}, {bpm} BPM, {duration:.0f}s)[/]")


# ===================================================================
# BUDGET command
# ===================================================================


@cli.command("budget")
@click.option("--days", default=30, help="Time window in days")
@click.pass_context
def budget_report(ctx: click.Context, days: int) -> None:
    """Show budget utilization report."""
    from src.db import queries

    async def _budget() -> None:
        async with _get_pool().connection() as conn:
            summary = await (
                await conn.execute(queries.GET_COST_SUMMARY, {"days": days})
            ).fetchone()

            providers = await (
                await conn.execute(queries.GET_COST_BY_PROVIDER, {"days": days})
            ).fetchall()

        if ctx.obj["json"]:
            _print_json(
                {
                    "days": days,
                    "summary": dict(summary) if summary else {},
                    "providers": [dict(p) for p in providers],
                }
            )
            return

        if not summary or not summary.get("total_cost"):
            console.print(f"[dim]No cost data in the last {days} days.[/]")
            return

        total = float(summary["total_cost"])
        avg = float(summary["avg_per_video"])
        count = summary["total_videos"]

        console.print(
            Panel(
                f"  Period:           Last {days} days\n"
                f"  Videos produced:  [bold]{count}[/]\n"
                f"  Total spend:      [bold yellow]${total:.2f}[/]\n"
                f"  Per-video avg:    [bold]${avg:.2f}[/]\n"
                f"  Daily avg:        [bold]${total / max(days, 1):.2f}[/]",
                title="Budget Report",
                border_style="yellow",
            )
        )

    _run(_budget())


# ===================================================================
# EXPORT command
# ===================================================================


@cli.group()
def export() -> None:
    """Export data for external analysis."""


@export.command("metrics")
@click.option("--channel", "channel_name", required=True, help="Channel handle or name")
@click.option("--format", "fmt", default="csv", type=click.Choice(["csv", "json"]))
@click.option("--days", default=90, help="Time window in days")
@click.option("--output", "output_file", default=None, help="Output file path (default: stdout)")
@click.pass_context
def export_metrics(
    ctx: click.Context,
    channel_name: str,
    fmt: str,
    days: int,
    output_file: str | None,
) -> None:
    """Export analytics to CSV or JSON for external analysis."""
    from src.db import queries
    from src.services.channel_manager import ChannelManager

    async def _export() -> None:
        mgr = ChannelManager(_get_settings(), _get_pool(), _get_http())
        channel_id = await mgr.resolve_channel_id(channel_name)
        if not channel_id:
            err_console.print(f"[red]Channel '{channel_name}' not found[/]")
            raise SystemExit(1)

        async with _get_pool().connection() as conn:
            rows = await (
                await conn.execute(
                    queries.EXPORT_VIDEO_METRICS,
                    {"channel_id": channel_id, "days": days},
                )
            ).fetchall()

        if not rows:
            err_console.print(f"[dim]No metrics data in the last {days} days.[/]")
            return

        if fmt == "json" or ctx.obj["json"]:
            output = orjson.dumps(
                [dict(r) for r in rows],
                default=_json_serializer,
                option=orjson.OPT_INDENT_2,
            ).decode()
        else:
            buf = io.StringIO()
            writer = csv.DictWriter(buf, fieldnames=list(rows[0].keys()))
            writer.writeheader()
            for r in rows:
                writer.writerow({k: str(v) for k, v in r.items()})
            output = buf.getvalue()

        if output_file:
            Path(output_file).write_text(output)
            console.print(f"[green]Exported {len(rows)} rows to {output_file}[/]")
        else:
            click.echo(output)

    _run(_export())


# ===================================================================
# COMMUNITY commands
# ===================================================================


@cli.group()
def community() -> None:
    """Community ecosystem — Discord, Patreon, topic submissions."""


@community.command("discord-notify")
@click.option("--video-id", required=True, help="Video UUID to notify about")
@click.pass_context
def community_discord_notify(ctx: click.Context, video_id: str) -> None:
    """Send a Discord notification for a published video."""
    from src.services.community import CommunityManager

    async def _notify() -> None:
        vid = uuid.UUID(video_id)
        mgr = CommunityManager(_get_settings(), _get_http(), _get_pool())

        # Fetch video metadata
        async with _get_pool().connection() as conn:
            row = await (
                await conn.execute(
                    "SELECT title, description, youtube_video_id, "
                    "video_length_seconds, topic FROM videos WHERE id = %(id)s",
                    {"id": vid},
                )
            ).fetchone()

        if not row:
            err_console.print(f"[red]Video {video_id} not found.[/]")
            return

        topic = row["topic"] if isinstance(row["topic"], dict) else {}
        notif = await mgr.notify_discord_new_video(
            video_id=vid,
            title=row["title"] or "",
            description=row["description"] or "",
            youtube_video_id=row["youtube_video_id"] or "",
            duration_seconds=row["video_length_seconds"] or 0,
            category=topic.get("category", ""),
        )

        if ctx.obj["json"]:
            _print_json(
                {
                    "success": notif.success,
                    "message_id": notif.message_id,
                    "error": notif.error,
                }
            )
        elif notif.success:
            console.print(f"[green]Discord notification sent[/] (message: {notif.message_id})")
        else:
            err_console.print(f"[red]Failed:[/] {notif.error}")

    _run(_notify())


@community.command("patreon-sync")
@click.pass_context
def community_patreon_sync(ctx: click.Context) -> None:
    """Sync Patreon membership data."""
    from src.services.community import CommunityManager

    async def _sync() -> None:
        mgr = CommunityManager(_get_settings(), _get_http(), _get_pool())
        result = await mgr.sync_patreon_members()

        if ctx.obj["json"]:
            _print_json(result.model_dump())
        else:
            console.print(
                Panel(
                    f"[bold]Patreon Sync Complete[/]\n\n"
                    f"  Total members:  {result.total_members}\n"
                    f"  New:            {result.new_members}\n"
                    f"  Updated:        {result.updated_members}\n"
                    f"  Churned:        {result.churned_members}\n"
                    f"  MRR:            ${result.total_mrr_cents / 100:.2f}",
                    title="Patreon Sync",
                    border_style="magenta",
                )
            )

    _run(_sync())


@community.group("submissions")
def community_submissions() -> None:
    """Manage topic submissions from the community."""


@community_submissions.command("list")
@click.option(
    "--status",
    default="new",
    type=click.Choice(["new", "reviewed", "accepted", "rejected", "produced"]),
    help="Filter by status",
)
@click.option("--limit", default=20, help="Max results")
@click.pass_context
def submissions_list(ctx: click.Context, status: str, limit: int) -> None:
    """List topic submissions by status."""
    from src.db import queries

    async def _list() -> None:
        async with _get_pool().connection() as conn:
            rows = await (
                await conn.execute(
                    queries.LIST_TOPIC_SUBMISSIONS,
                    {"status": status, "limit": limit, "offset": 0},
                )
            ).fetchall()

        if ctx.obj["json"]:
            _print_json([dict(r) for r in rows])
            return

        if not rows:
            console.print(f"[dim]No submissions with status '{status}'.[/]")
            return

        table = Table(title=f"Topic Submissions ({status})", box=box.ROUNDED)
        table.add_column("ID", style="dim", no_wrap=True)
        table.add_column("Case Name", style="bold cyan")
        table.add_column("Source", justify="center")
        table.add_column("Submitter")
        table.add_column("Score", justify="right")
        table.add_column("Created", style="dim")

        for r in rows:
            score_str = f"{r['score']:.1f}" if r.get("score") else "-"
            table.add_row(
                str(r["id"])[:8],
                (r["case_name"] or "")[:50],
                r["source"] or "-",
                r["submitter_name"] or "-",
                score_str,
                r["created_at"].strftime("%Y-%m-%d") if r.get("created_at") else "-",
            )

        console.print(table)

    _run(_list())


@community_submissions.command("review")
@click.argument("submission_id")
@click.option("--accept", "action", flag_value="accepted", help="Accept the submission")
@click.option("--reject", "action", flag_value="rejected", help="Reject the submission")
@click.pass_context
def submissions_review(ctx: click.Context, submission_id: str, action: str | None) -> None:
    """Accept or reject a topic submission."""
    from src.services.community import CommunityManager

    if not action:
        err_console.print("[red]Specify --accept or --reject[/]")
        return

    async def _review() -> None:
        mgr = CommunityManager(_get_settings(), _get_http(), _get_pool())
        result = await mgr.review_submission(
            submission_id=uuid.UUID(submission_id),
            status=action,
        )

        if result is None:
            err_console.print(f"[red]Submission {submission_id} not found.[/]")
            return

        if ctx.obj["json"]:
            _print_json(result.model_dump())
        else:
            color = "green" if action == "accepted" else "red"
            console.print(
                f"[{color}]{action.upper()}[/]: {result.case_name} (score: {result.score or 'N/A'})"
            )

    _run(_review())


@community.command("metrics")
@click.option("--channel", required=True, help="Channel handle or name")
@click.pass_context
def community_metrics(ctx: click.Context, channel: str) -> None:
    """Show community health metrics for a channel."""
    from src.services.channel_manager import ChannelManager
    from src.services.community import CommunityManager

    async def _metrics() -> None:
        ch_mgr = ChannelManager(_get_settings(), _get_pool(), _get_http())
        channel_id = await ch_mgr.resolve_channel_id(channel)
        if not channel_id:
            err_console.print(f"[red]Channel '{channel}' not found.[/]")
            return

        mgr = CommunityManager(_get_settings(), _get_http(), _get_pool())
        m = await mgr.get_community_metrics(channel_id)

        if ctx.obj["json"]:
            _print_json(m.model_dump())
        else:
            mrr = float(m.patreon_mrr_usd)
            console.print(
                Panel(
                    f"[bold]Community Metrics[/]\n\n"
                    f"  Discord members:       {m.discord_members_total:,}\n"
                    f"  Discord active (7d):   {m.discord_active_7d:,}\n"
                    f"  Patreon patrons:       {m.patreon_patron_count:,}\n"
                    f"  Patreon MRR:           ${mrr:,.2f}\n"
                    f"  Submissions (month):   {m.submissions_this_month}\n"
                    f"  Community-sourced:     {m.community_sourced_videos}\n"
                    f"  Patron retention:      {m.patron_retention_rate:.0%}",
                    title=f"Community — {channel}",
                    border_style="blue",
                )
            )

    _run(_metrics())


# ===================================================================
# RESEARCH commands
# ===================================================================


@cli.group()
def research() -> None:
    """Research database and FOIA tracking."""


@research.command("search")
@click.option("--query", "-q", required=True, help="Full-text search query")
@click.option("--source", "source_type", default=None, help="Filter by source type")
@click.option("--limit", default=20, help="Max results")
@click.pass_context
def research_search(ctx: click.Context, query: str, source_type: str | None, limit: int) -> None:
    """Search across all research sources."""
    from src.db import queries

    async def _search() -> None:
        async with _get_pool().connection() as conn:
            rows = await (
                await conn.execute(
                    queries.SEARCH_RESEARCH_SOURCES,
                    {
                        "query": query,
                        "source_type": source_type,
                        "date_from": None,
                        "date_to": None,
                        "limit": limit,
                        "offset": 0,
                    },
                )
            ).fetchall()

        if ctx.obj["json"]:
            _print_json([dict(r) for r in rows])
            return

        if not rows:
            console.print(f"[dim]No results for '{query}'.[/]")
            return

        table = Table(title=f'Research Sources — "{query}"', box=box.ROUNDED)
        table.add_column("ID", style="dim", no_wrap=True)
        table.add_column("Type", justify="center")
        table.add_column("Title", style="bold cyan")
        table.add_column("Source")
        table.add_column("Date", style="dim")
        table.add_column("Rank", justify="right")

        for r in rows:
            table.add_row(
                str(r["id"])[:8],
                r.get("source_type", "-"),
                (r.get("title", "") or "")[:60],
                r.get("source_name", "-") or "-",
                str(r["publication_date"]) if r.get("publication_date") else "-",
                f"{r.get('rank', 0):.3f}" if r.get("rank") else "-",
            )

        console.print(table)

    _run(_search())


@research.command("collect")
@click.option("--query", "-q", required=True, help="Search query for collection")
@click.option("--case-id", default=None, help="Link to case file UUID")
@click.option(
    "--sources",
    default="sec_filing,court_document,doj_press_release,ftc_action",
    help="Comma-separated source types",
)
@click.pass_context
def research_collect(ctx: click.Context, query: str, case_id: str | None, sources: str) -> None:
    """Trigger automated source collection from public records."""
    from src.models.research import CollectionRequest
    from src.services.research_collector import ResearchCollector

    async def _collect() -> None:
        source_list = [s.strip() for s in sources.split(",") if s.strip()]
        req = CollectionRequest(
            query=query,
            case_file_id=uuid.UUID(case_id) if case_id else None,
            source_types=source_list,  # type: ignore[arg-type]
        )
        collector = ResearchCollector(_get_settings(), _get_http(), _get_pool())
        result = await collector.collect(req)

        if ctx.obj["json"]:
            _print_json(result.model_dump())
        else:
            console.print(
                Panel(
                    f"[bold]Collection Complete[/]\n\n"
                    f"  Query:             {query}\n"
                    f"  Sources searched:  {', '.join(result.source_types_searched)}\n"
                    f"  Sources found:     {result.sources_found}\n"
                    f"  Sources stored:    {result.sources_stored}\n"
                    f"  Entities:          {result.entities_extracted}",
                    title="Research Collection",
                    border_style="cyan",
                )
            )

    _run(_collect())


@research.command("cases")
@click.option("--category", default=None, help="Filter by category")
@click.option("--status", default=None, help="Filter by status")
@click.option("--limit", default=20, help="Max results")
@click.pass_context
def research_cases(
    ctx: click.Context, category: str | None, status: str | None, limit: int
) -> None:
    """List case files."""
    from src.db import queries

    async def _list() -> None:
        async with _get_pool().connection() as conn:
            rows = await (
                await conn.execute(
                    queries.LIST_CASE_FILES,
                    {"category": category, "status": status, "limit": limit, "offset": 0},
                )
            ).fetchall()

        if ctx.obj["json"]:
            _print_json([dict(r) for r in rows])
            return

        if not rows:
            console.print("[dim]No case files found.[/]")
            return

        table = Table(title="Case Files", box=box.ROUNDED)
        table.add_column("ID", style="dim", no_wrap=True)
        table.add_column("Case Name", style="bold cyan")
        table.add_column("Category")
        table.add_column("Status")
        table.add_column("Sources", justify="right")
        table.add_column("Updated", style="dim")

        for r in rows:
            table.add_row(
                str(r["id"])[:8],
                (r.get("case_name", "") or "")[:50],
                r.get("category", "-"),
                r.get("status", "-"),
                str(r.get("source_count", 0)),
                r["updated_at"].strftime("%Y-%m-%d") if r.get("updated_at") else "-",
            )

        console.print(table)

    _run(_list())


@research.command("case-build")
@click.option("--name", required=True, help="Case name / search query")
@click.option(
    "--category",
    default="other",
    type=click.Choice(
        [
            "corporate_fraud",
            "ponzi_scheme",
            "art_forgery",
            "cybercrime",
            "money_laundering",
            "embezzlement",
            "insurance_fraud",
            "identity_theft",
            "murder",
            "kidnapping",
            "organized_crime",
            "political_corruption",
            "environmental_crime",
            "trafficking",
            "other",
        ]
    ),
    help="Case category",
)
@click.pass_context
def research_case_build(ctx: click.Context, name: str, category: str) -> None:
    """Build a full case file — collects from all sources and extracts entities."""
    from src.services.research_collector import ResearchCollector

    async def _build() -> None:
        collector = ResearchCollector(_get_settings(), _get_http(), _get_pool())
        case = await collector.build_case_file(name, category=category)

        if ctx.obj["json"]:
            _print_json(case.model_dump())
        else:
            console.print(
                Panel(
                    f"[bold]Case File Built[/]\n\n"
                    f"  ID:         {str(case.id)[:8]}...\n"
                    f"  Name:       {case.case_name}\n"
                    f"  Category:   {case.category}\n"
                    f"  Status:     {case.status}\n"
                    f"  Sources:    {case.source_count}\n"
                    f"  Entities:   {len(case.key_entities or [])}",
                    title="Case File",
                    border_style="green",
                )
            )

    _run(_build())


@research.command("foia-list")
@click.option("--status", default=None, help="Filter by status")
@click.option("--overdue", is_flag=True, help="Show only overdue requests")
@click.pass_context
def research_foia_list(ctx: click.Context, status: str | None, overdue: bool) -> None:
    """List FOIA requests."""
    from src.services.foia_tracker import FOIATracker

    async def _list() -> None:
        tracker = FOIATracker(_get_settings(), _get_pool(), _get_http())
        if overdue:
            rows = await tracker.get_overdue_requests()
        else:
            rows = await tracker.get_pending_requests(status=status)

        if ctx.obj["json"]:
            _print_json([r.model_dump() for r in rows])
            return

        if not rows:
            label = "overdue" if overdue else f"status='{status}'" if status else "all"
            console.print(f"[dim]No FOIA requests ({label}).[/]")
            return

        title = "Overdue FOIA Requests" if overdue else "FOIA Requests"
        table = Table(title=title, box=box.ROUNDED)
        table.add_column("ID", style="dim", no_wrap=True)
        table.add_column("Agency", style="bold")
        table.add_column("Description")
        table.add_column("Status")
        table.add_column("Filed", style="dim")
        table.add_column("Expected", style="dim")
        table.add_column("Docs", justify="right")

        for r in rows:
            status_style = "[red]" if r.is_overdue else ""
            status_end = "[/]" if r.is_overdue else ""
            table.add_row(
                str(r.id)[:8],
                r.agency,
                (r.description or "")[:40],
                f"{status_style}{r.status}{status_end}",
                str(r.date_filed) if r.date_filed else "-",
                str(r.expected_response_date) if r.expected_response_date else "-",
                str(r.documents_received),
            )

        console.print(table)

    _run(_list())


@research.command("foia-file")
@click.option("--agency", required=True, help="Agency name (DOJ, FBI, SEC, etc.)")
@click.option("--description", required=True, help="FOIA request description")
@click.option("--case-id", default=None, help="Link to case file UUID")
@click.option(
    "--method",
    default="electronic",
    type=click.Choice(["electronic", "mail", "email"]),
    help="Filing method",
)
@click.pass_context
def research_foia_file(
    ctx: click.Context, agency: str, description: str, case_id: str | None, method: str
) -> None:
    """Track a new FOIA request."""
    from src.models.research import FOIARequestInput
    from src.services.foia_tracker import FOIATracker

    async def _file() -> None:
        tracker = FOIATracker(_get_settings(), _get_pool(), _get_http())
        inp = FOIARequestInput(
            agency=agency,
            description=description,
            case_file_id=uuid.UUID(case_id) if case_id else None,
            method=method,  # type: ignore[arg-type]
        )
        result = await tracker.file_request(inp)

        if ctx.obj["json"]:
            _print_json(result.model_dump())
        else:
            console.print(
                Panel(
                    f"[bold]FOIA Request Filed[/]\n\n"
                    f"  ID:         {str(result.id)[:8]}...\n"
                    f"  Agency:     {result.agency}\n"
                    f"  Filed:      {result.date_filed}\n"
                    f"  Expected:   {result.expected_response_date}\n"
                    f"  Status:     {result.status}",
                    title="FOIA Request",
                    border_style="yellow",
                )
            )

    _run(_file())


@research.command("foia-update")
@click.argument("foia_id")
@click.option("--status", default=None, help="New status")
@click.option("--tracking-number", default=None, help="Tracking number from agency")
@click.option("--notes", default=None, help="Additional notes")
@click.option(
    "--docs", "documents_received", default=None, type=int, help="Documents received count"
)
@click.pass_context
def research_foia_update(
    ctx: click.Context,
    foia_id: str,
    status: str | None,
    tracking_number: str | None,
    notes: str | None,
    documents_received: int | None,
) -> None:
    """Update a FOIA request status."""
    from src.models.research import FOIAUpdateInput
    from src.services.foia_tracker import FOIATracker

    async def _update() -> None:
        tracker = FOIATracker(_get_settings(), _get_pool(), _get_http())
        update = FOIAUpdateInput(
            status=status,  # type: ignore[arg-type]
            tracking_number=tracking_number,
            notes=notes,
            documents_received=documents_received,
        )
        try:
            result = await tracker.update_status(uuid.UUID(foia_id), update)
        except ValueError as exc:
            err_console.print(f"[red]{exc}[/]")
            raise SystemExit(1) from exc

        if ctx.obj["json"]:
            _print_json(result.model_dump())
        else:
            console.print(f"[green]Updated[/] FOIA {str(result.id)[:8]} → status={result.status}")

    _run(_update())


# ===================================================================
# SERIES commands
# ===================================================================


@cli.group()
def series() -> None:
    """Manage multi-part series and seasons."""


@series.command("create")
@click.option("--channel", "channel_name", required=True, help="Channel handle or name")
@click.option("--title", required=True, help="Series title")
@click.option(
    "--type",
    "series_type",
    required=True,
    type=click.Choice(["multi_part", "thematic_season", "ongoing_arc"]),
    help="Series type",
)
@click.option(
    "--episodes", "planned_episodes", required=True, type=int, help="Number of planned episodes"
)
@click.option("--description", default="", help="Series description")
@click.pass_context
def series_create(
    ctx: click.Context,
    channel_name: str,
    title: str,
    series_type: str,
    planned_episodes: int,
    description: str,
) -> None:
    """Create a new series for a channel."""
    from src.models.series import SeriesInput
    from src.services.channel_manager import ChannelManager
    from src.services.series_planner import SeriesPlanner

    async def _create() -> None:
        mgr = ChannelManager(_get_settings(), _get_pool(), _get_http())
        channel_id = await mgr.resolve_channel_id(channel_name)
        if not channel_id:
            err_console.print(f"[red]Channel '{channel_name}' not found[/]")
            raise SystemExit(1)

        planner = SeriesPlanner(_get_settings(), _get_http(), _get_pool())
        inp = SeriesInput(
            title=title,
            description=description,
            channel_id=channel_id,
            series_type=series_type,  # type: ignore[arg-type]
            planned_episodes=planned_episodes,
        )
        result = await planner.create_series(inp)

        if ctx.obj["json"]:
            _print_json(result.model_dump())
        else:
            console.print(
                Panel(
                    f"[bold green]Series created[/]\n\n"
                    f"  ID:       {result.id}\n"
                    f"  Title:    {result.title}\n"
                    f"  Type:     {result.series_type}\n"
                    f"  Episodes: {result.planned_episodes}\n"
                    f"  Status:   {result.status}",
                    title="Series",
                )
            )

    _run(_create())


@series.command("plan")
@click.argument("series_id")
@click.pass_context
def series_plan(ctx: click.Context, series_id: str) -> None:
    """Generate a narrative arc for all episodes using Claude."""
    from src.services.series_planner import SeriesPlanner

    async def _plan() -> None:
        planner = SeriesPlanner(_get_settings(), _get_http(), _get_pool())
        try:
            arc = await planner.plan_series_arc(uuid.UUID(series_id))
        except ValueError as exc:
            err_console.print(f"[red]{exc}[/]")
            raise SystemExit(1) from exc

        if ctx.obj["json"]:
            _print_json(arc.model_dump())
        else:
            console.print(f"\n[bold]Series Arc — {arc.series_id}[/]\n")
            table = Table(box=box.ROUNDED)
            table.add_column("#", style="dim", width=3)
            table.add_column("Title", style="bold")
            table.add_column("Core Question")
            table.add_column("Key Revelation")
            table.add_column("Hook Type")
            for ep in arc.episodes:
                table.add_row(
                    str(ep.episode_number),
                    ep.title,
                    ep.core_question,
                    ep.key_revelation,
                    ep.suggested_hook_type,
                )
            console.print(table)
            if arc.cost:
                console.print(
                    f"\n[dim]Cost: ${arc.cost.cost_usd:.4f} "
                    f"({arc.cost.model}, {arc.cost.input_tokens}+{arc.cost.output_tokens} tokens)[/]"
                )

    _run(_plan())


@series.command("status")
@click.option("--channel", "channel_name", required=True, help="Channel handle or name")
@click.option("--status", "status_filter", default=None, help="Filter by status")
@click.pass_context
def series_status(ctx: click.Context, channel_name: str, status_filter: str | None) -> None:
    """List series for a channel with episode counts."""
    from src.db import queries
    from src.services.channel_manager import ChannelManager

    async def _status() -> None:
        mgr = ChannelManager(_get_settings(), _get_pool(), _get_http())
        channel_id = await mgr.resolve_channel_id(channel_name)
        if not channel_id:
            err_console.print(f"[red]Channel '{channel_name}' not found[/]")
            raise SystemExit(1)

        from psycopg.rows import dict_row

        async with _get_pool().connection() as conn, conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(
                queries.LIST_SERIES,
                {
                    "channel_id": channel_id,
                    "status_filter": status_filter,
                    "limit": 50,
                    "offset": 0,
                },
            )
            rows = await cur.fetchall()

        if ctx.obj["json"]:
            _print_json([dict(r) for r in rows])
        else:
            if not rows:
                console.print("[dim]No series found.[/]")
                return
            table = Table(title=f"Series — {channel_name}", box=box.ROUNDED)
            table.add_column("ID", style="dim", width=8)
            table.add_column("Title", style="bold")
            table.add_column("Type")
            table.add_column("Episodes")
            table.add_column("Status")
            table.add_column("Playlist")
            for r in rows:
                table.add_row(
                    str(r["id"])[:8],
                    r["title"],
                    r["series_type"],
                    str(r["planned_episodes"]),
                    r["status"],
                    r.get("youtube_playlist_id") or "—",
                )
            console.print(table)

    _run(_status())


@series.command("analytics")
@click.argument("series_id")
@click.pass_context
def series_analytics(ctx: click.Context, series_id: str) -> None:
    """Show per-episode analytics for a series."""
    from src.services.series_planner import SeriesPlanner

    async def _analytics() -> None:
        planner = SeriesPlanner(_get_settings(), _get_http(), _get_pool())
        try:
            analytics = await planner.get_series_analytics(uuid.UUID(series_id))
        except ValueError as exc:
            err_console.print(f"[red]{exc}[/]")
            raise SystemExit(1) from exc

        if ctx.obj["json"]:
            _print_json(analytics.model_dump())
        else:
            console.print(f"\n[bold]Series Analytics — {analytics.series_title}[/]\n")
            table = Table(box=box.ROUNDED)
            table.add_column("#", style="dim", width=3)
            table.add_column("Title", style="bold")
            table.add_column("Views", justify="right")
            table.add_column("Avg Duration(s)", justify="right")
            table.add_column("CTR %", justify="right")
            table.add_column("Revenue", justify="right")
            for ep in analytics.episode_metrics:
                table.add_row(
                    str(ep.episode_number),
                    ep.title,
                    f"{ep.views:,}" if ep.views else "—",
                    f"{ep.avg_view_duration_seconds:.1f}" if ep.avg_view_duration_seconds else "—",
                    f"{ep.ctr:.2f}" if ep.ctr else "—",
                    f"${ep.revenue:.2f}" if ep.revenue else "—",
                )
            console.print(table)

            console.print(f"\n  Total views:     {analytics.total_views:,}")
            console.print(f"  Avg session:     {analytics.avg_session_depth:.1f} episodes")
            if analytics.series_vs_standalone_multiplier:
                console.print(
                    f"  Series vs solo:  {analytics.series_vs_standalone_multiplier:.1f}x"
                )
            console.print()

    _run(_analytics())


# ===================================================================
# DISCOVERY commands
# ===================================================================


@cli.group()
def discover() -> None:
    """Topic discovery — scan Reddit, GDELT, advisories, etc. for video ideas."""


def _build_supabase_client() -> Any:
    """Lazy supabase client — keeps the dep optional at CLI startup."""
    from supabase import create_client

    s = _get_settings()
    return create_client(s.database.url, s.database.service_role_key)


@discover.command("run-all")
@click.option("--score/--no-score", default=False, help="Score candidates with Claude Haiku")
@click.option("--verbose", "-v", is_flag=True, help="Verbose logging")
@click.pass_context
def discover_run_all(ctx: click.Context, score: bool, verbose: bool) -> None:
    """Run every discovery source, dedupe, and persist new topics."""
    import logging as _logging

    from src.services.discovery import DiscoveryOrchestrator

    if verbose:
        _logging.basicConfig(level=_logging.DEBUG, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    else:
        _logging.basicConfig(level=_logging.INFO, format="%(message)s")

    async def _run_all() -> None:
        orch = DiscoveryOrchestrator(_build_supabase_client(), _get_settings())
        result = await orch.run_all(score=score)
        if ctx.obj["json"]:
            _print_json(result)
        else:
            console.print(
                f"\n[bold]Discovery complete[/]  "
                f"found={result['total_candidates']}  saved={result['total_saved']}  "
                f"errors={len(result['errors'])}\n"
            )
            for name, info in result["sources"].items():
                color = "green" if info["status"] == "ok" else "red"
                console.print(f"  [{color}]{info['status']:5s}[/]  {name:15s}  {info['candidates']} candidates")
            if result.get("scoring"):
                console.print(f"\nScoring: {result['scoring']}")

    _run(_run_all())


@discover.command("run-source")
@click.argument("source_name")
@click.option("--score/--no-score", default=False, help="Score candidates with Claude Haiku")
@click.option("--verbose", "-v", is_flag=True, help="Verbose logging")
@click.pass_context
def discover_run_source(ctx: click.Context, source_name: str, score: bool, verbose: bool) -> None:
    """Run a single discovery source (e.g. reddit, gdelt, advisory)."""
    import logging as _logging

    from src.services.discovery import DiscoveryOrchestrator

    if verbose:
        _logging.basicConfig(level=_logging.DEBUG, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    else:
        _logging.basicConfig(level=_logging.INFO, format="%(message)s")

    async def _run_one() -> None:
        orch = DiscoveryOrchestrator(_build_supabase_client(), _get_settings())
        try:
            result = await orch.run_source(source_name, score=score)
        except ValueError as exc:
            err_console.print(f"[red]{exc}[/]")
            raise SystemExit(1) from exc
        if ctx.obj["json"]:
            _print_json(result)
        else:
            console.print(
                f"\n[bold]{result['source']}[/]  found={result['candidates_found']}  "
                f"saved={result['candidates_saved']}\n"
            )

    _run(_run_one())


@discover.command("list-sources")
@click.pass_context
def discover_list_sources(ctx: click.Context) -> None:
    """Show every discovery source registered in the orchestrator."""
    from src.services.discovery.orchestrator import SOURCE_REGISTRY

    sources = sorted(SOURCE_REGISTRY.keys())
    if ctx.obj["json"]:
        _print_json({"sources": sources})
        return
    table = Table(title="Discovery sources", box=box.SIMPLE)
    table.add_column("Source", style="cyan")
    table.add_column("Class", style="dim")
    for name in sources:
        cls = SOURCE_REGISTRY[name]
        table.add_row(name, cls.__name__)
    console.print(table)


@discover.command("show-backlog")
@click.option("--limit", default=20, type=int, help="Number of topics to show")
@click.pass_context
def discover_show_backlog(ctx: click.Context, limit: int) -> None:
    """Show top unassigned discovered topics ordered by composite score."""
    sb = _build_supabase_client()
    res = (
        sb.table("discovered_topics")
        .select("id, title, category, composite_score, priority, source_signals, created_at")
        .is_("used_in_video_id", "null")
        .order("composite_score", desc=True)
        .limit(limit)
        .execute()
    )
    rows = res.data or []
    if ctx.obj["json"]:
        _print_json({"count": len(rows), "topics": rows})
        return
    if not rows:
        console.print("[yellow]Backlog is empty.[/]")
        return
    table = Table(title=f"Top {len(rows)} unassigned topics", box=box.SIMPLE)
    table.add_column("Score", justify="right", style="bold")
    table.add_column("Priority", style="cyan")
    table.add_column("Category", style="dim")
    table.add_column("Title", overflow="fold")
    table.add_column("Source", style="dim")
    for r in rows:
        signals = r.get("source_signals") or {}
        src = signals.get("source", "?") if isinstance(signals, dict) else "?"
        table.add_row(
            f"{r.get('composite_score', 0):.1f}",
            str(r.get("priority") or ""),
            str(r.get("category") or ""),
            str(r.get("title") or "")[:80],
            src,
        )
    console.print(table)


# ===================================================================
# Entry point
# ===================================================================


def main() -> None:
    """CLI entry point."""
    cli()


if __name__ == "__main__":
    main()
