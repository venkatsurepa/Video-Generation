#!/usr/bin/env python3
"""CLI tool for provider benchmarking and self-hosting cost analysis.

Usage:
    python -m backend.scripts.benchmark_cli tts \\
        --text "On the night of March 15th..." \\
        --providers fish_audio,chatterbox

    python -m backend.scripts.benchmark_cli images \\
        --prompt "Dark office, scattered documents..." \\
        --providers fal_ai,local_flux

    python -m backend.scripts.benchmark_cli break-even \\
        --provider fish_audio \\
        --current-cost 11.00

    python -m backend.scripts.benchmark_cli migrate \\
        --from fal_ai --to local_flux --plan-only
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from decimal import Decimal
from pathlib import Path

# Add backend to path so we can import src.*
_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))


async def cmd_benchmark_tts(args: argparse.Namespace) -> None:
    """Benchmark TTS providers."""
    import httpx

    from src.config import get_settings
    from src.services.benchmark import ProviderBenchmark

    settings = get_settings()
    providers = [p.strip() for p in args.providers.split(",")]

    async with httpx.AsyncClient() as http:
        bench = ProviderBenchmark(settings, None, http)  # type: ignore[arg-type]
        result = await bench.benchmark_tts(
            text=args.text,
            providers=providers,
            voice_id=args.voice_id or "default",
        )

    print("\n=== TTS Benchmark Results ===\n")
    for sample in result.samples:
        status = "OK" if sample.error is None else f"FAILED: {sample.error}"
        print(
            f"  {sample.provider:20s}  {sample.latency_ms:6d}ms  ${sample.cost_usd:10.6f}  {status}"
        )
        if sample.output_path:
            print(f"  {'':20s}  Output: {sample.output_path}")
    print()
    print(f"  Fastest:  {result.fastest_provider}")
    print(f"  Cheapest: {result.cheapest_provider}")

    if args.json:
        print("\n" + result.model_dump_json(indent=2))


async def cmd_benchmark_images(args: argparse.Namespace) -> None:
    """Benchmark image providers."""
    import httpx

    from src.config import get_settings
    from src.services.benchmark import ProviderBenchmark

    settings = get_settings()
    providers = [p.strip() for p in args.providers.split(",")]

    async with httpx.AsyncClient() as http:
        bench = ProviderBenchmark(settings, None, http)  # type: ignore[arg-type]
        result = await bench.benchmark_images(
            prompt=args.prompt,
            providers=providers,
            width=args.width,
            height=args.height,
        )

    print("\n=== Image Benchmark Results ===\n")
    for sample in result.samples:
        status = "OK" if sample.error is None else f"FAILED: {sample.error}"
        print(
            f"  {sample.provider:20s}  {sample.latency_ms:6d}ms  ${sample.cost_usd:10.6f}  {status}"
        )
        if sample.output_path:
            print(f"  {'':20s}  Output: {sample.output_path}")
    print()
    print(f"  Fastest:  {result.fastest_provider}")
    print(f"  Cheapest: {result.cheapest_provider}")

    if args.json:
        print("\n" + result.model_dump_json(indent=2))


async def cmd_break_even(args: argparse.Namespace) -> None:
    """Calculate break-even point for self-hosting."""
    import httpx

    from src.config import get_settings
    from src.services.benchmark import ProviderBenchmark

    settings = get_settings()

    async with httpx.AsyncClient() as http:
        bench = ProviderBenchmark(settings, None, http)  # type: ignore[arg-type]
        analysis = await bench.calculate_break_even(
            current_provider=args.provider,
            current_monthly_cost=Decimal(args.current_cost),
            target_provider=args.target or None,
            current_volume=args.volume or 0,
        )

    print("\n=== Break-Even Analysis ===\n")
    print(f"  Current provider:     {analysis.current_provider}")
    print(f"  Target provider:      {analysis.target_provider}")
    print(f"  Current monthly cost: ${analysis.current_monthly_cost_usd}")
    print()
    print(f"  GPU hosting:          ${analysis.gpu_estimate.monthly_gpu_cost_usd}/month")
    print(f"    GPU model:          {analysis.gpu_estimate.gpu_model}")
    print(f"    Hours/month:        {analysis.gpu_estimate.monthly_hours}")
    print(f"    Storage:            ${analysis.gpu_estimate.monthly_storage_usd}/month")
    print(f"    Bandwidth:          ${analysis.gpu_estimate.monthly_bandwidth_usd}/month")
    print()
    print(f"  Maintenance:          ${analysis.maintenance.monthly_cost_usd}/month")
    print(f"    Hours/month:        {analysis.maintenance.hours_per_month}")
    print(f"    Rate:               ${analysis.maintenance.hourly_rate_usd}/hour")
    print()
    print(f"  Total self-hosted:    ${analysis.total_self_hosted_monthly_usd}/month")
    print(f"  Monthly savings:      ${analysis.monthly_savings_usd}/month")
    print(f"  Break-even volume:    {analysis.break_even_volume} units/month")
    print(f"  Setup cost:           ${analysis.setup_cost_usd}")
    print(f"  Payback period:       {analysis.payback_period_months} months")
    print()
    print(f"  RECOMMENDATION:       {analysis.recommendation.upper()}")
    print(f"  Reasoning:            {analysis.reasoning}")

    if analysis.risk_factors:
        print("\n  Risk Factors:")
        for risk in analysis.risk_factors:
            print(f"    [{risk.severity:6s}] {risk.category}: {risk.description}")
            if risk.mitigation:
                print(f"             Mitigation: {risk.mitigation}")

    if args.json:
        print("\n" + analysis.model_dump_json(indent=2))


async def cmd_migrate(args: argparse.Namespace) -> None:
    """Generate a migration plan."""
    import httpx

    from src.config import get_settings
    from src.services.benchmark import ProviderBenchmark

    settings = get_settings()

    async with httpx.AsyncClient() as http:
        bench = ProviderBenchmark(settings, None, http)  # type: ignore[arg-type]
        plan = await bench.generate_migration_plan(
            from_provider=args.from_provider,
            to_provider=args.to_provider,
        )

    print(f"\n=== Migration Plan: {plan.from_provider} → {plan.to_provider} ===\n")
    print(
        f"  Estimated effort: {plan.total_estimated_hours} hours over "
        f"{plan.estimated_calendar_days} days\n"
    )

    for step in plan.steps:
        deps = f" (depends on: {step.dependencies})" if step.dependencies else ""
        print(f"  Step {step.step_number}: {step.title}{deps}")
        print(f"    {step.description}")
        print(f"    Estimated: {step.estimated_hours} hours")
        if step.rollback_plan:
            print(f"    Rollback:  {step.rollback_plan}")
        print()

    print(f"  Rollback strategy: {plan.rollback_strategy}\n")
    print("  Success criteria:")
    for criterion in plan.success_criteria:
        print(f"    - {criterion}")

    if args.json:
        print("\n" + plan.model_dump_json(indent=2))


def main() -> None:
    parser = argparse.ArgumentParser(
        description="CrimeMill provider benchmarking and self-hosting analysis",
        prog="benchmark",
    )
    parser.add_argument("--json", action="store_true", help="Output full JSON result")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # -- tts --
    tts_parser = subparsers.add_parser("tts", help="Benchmark TTS providers")
    tts_parser.add_argument("--text", required=True, help="Text to synthesize")
    tts_parser.add_argument(
        "--providers",
        required=True,
        help="Comma-separated provider names (e.g., fish_audio,chatterbox)",
    )
    tts_parser.add_argument("--voice-id", default="default", help="Voice ID")

    # -- images --
    img_parser = subparsers.add_parser("images", help="Benchmark image providers")
    img_parser.add_argument("--prompt", required=True, help="Image prompt")
    img_parser.add_argument(
        "--providers",
        required=True,
        help="Comma-separated provider names (e.g., fal_ai,local_flux)",
    )
    img_parser.add_argument("--width", type=int, default=1920)
    img_parser.add_argument("--height", type=int, default=1080)

    # -- break-even --
    be_parser = subparsers.add_parser("break-even", help="Calculate break-even point")
    be_parser.add_argument(
        "--provider",
        required=True,
        help="Current API provider (e.g., fish_audio)",
    )
    be_parser.add_argument(
        "--current-cost",
        required=True,
        help="Current monthly cost in USD (e.g., 11.00)",
    )
    be_parser.add_argument("--target", default=None, help="Target self-hosted provider")
    be_parser.add_argument("--volume", type=int, default=0, help="Current monthly volume")

    # -- migrate --
    mig_parser = subparsers.add_parser("migrate", help="Generate migration plan")
    mig_parser.add_argument(
        "--from",
        dest="from_provider",
        required=True,
        help="Source API provider",
    )
    mig_parser.add_argument(
        "--to",
        dest="to_provider",
        required=True,
        help="Target self-hosted provider",
    )
    mig_parser.add_argument(
        "--plan-only",
        action="store_true",
        help="Only show the plan, don't execute anything",
    )

    args = parser.parse_args()

    handlers = {
        "tts": cmd_benchmark_tts,
        "images": cmd_benchmark_images,
        "break-even": cmd_break_even,
        "migrate": cmd_migrate,
    }
    handler = handlers[args.command]
    asyncio.run(handler(args))


if __name__ == "__main__":
    main()
