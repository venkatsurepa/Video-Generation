"""Provider benchmarking service — compare API vs self-hosted models.

Provides tools to:
  1. Run the same task through multiple providers and compare latency/cost
  2. Calculate break-even points for self-hosting migration
  3. Generate step-by-step migration plans with rollback strategies

Usage:
    bench = ProviderBenchmark(settings, db_pool, http_client)
    result = await bench.benchmark_tts("On the night of...", ["fish_audio", "chatterbox"])
    analysis = await bench.calculate_break_even("fish_audio", Decimal("11.00"))
"""

from __future__ import annotations

import time
from decimal import Decimal
from typing import TYPE_CHECKING, Literal

import structlog

from src.models.benchmark import (
    BenchmarkResult,
    BenchmarkSample,
    BreakEvenAnalysis,
    GPUCostEstimate,
    MaintenanceCost,
    MigrationPlan,
    MigrationStep,
    ProviderComparison,
    RiskFactor,
)
from src.services.providers import ProviderFactory

if TYPE_CHECKING:
    import httpx
    from psycopg_pool import AsyncConnectionPool

    from src.config import Settings

logger = structlog.get_logger()


# ---------------------------------------------------------------------------
# GPU cost presets per provider
# ---------------------------------------------------------------------------

_GPU_PRESETS: dict[str, GPUCostEstimate] = {
    "chatterbox": GPUCostEstimate(
        provider="runpod",
        gpu_model="RTX 4090",
        hourly_rate_usd=Decimal("0.50"),
        # Serverless: pay only for active generation (~10 hrs/month at 50 videos)
        monthly_hours=Decimal("10"),
    ),
    "kokoro": GPUCostEstimate(
        provider="vast_ai",
        gpu_model="CPU (no GPU)",
        hourly_rate_usd=Decimal("0.01"),  # VPS cost
        monthly_hours=Decimal("730"),
    ),
    "local_flux": GPUCostEstimate(
        provider="vast_ai",
        gpu_model="RTX 4090",
        hourly_rate_usd=Decimal("0.50"),
        monthly_hours=Decimal("40"),  # ~40 hrs/month for 100 videos
    ),
    "ace_step": GPUCostEstimate(
        provider="vast_ai",
        gpu_model="RTX 3090",
        hourly_rate_usd=Decimal("0.40"),
        monthly_hours=Decimal("2"),  # ~2 hrs for batch generating 30 tracks
    ),
}

# Per-unit API costs for break-even calculation
_API_UNIT_COSTS: dict[str, tuple[str, Decimal]] = {
    "fish_audio": ("character", Decimal("0.0000647")),
    "fal_ai": ("image", Decimal("0.003")),
    "epidemic_sound_library": ("track", Decimal("0")),
    "anthropic": ("1k_tokens", Decimal("0.003")),
}

# Self-hosted per-unit costs
_SELF_HOSTED_UNIT_COSTS: dict[str, tuple[str, Decimal]] = {
    "chatterbox": ("character", Decimal("0.0000065")),
    "kokoro": ("character", Decimal("0.0000001")),
    "local_flux": ("image", Decimal("0.0006")),
    "ace_step": ("track", Decimal("0.003")),
}

# Standard risk factors for self-hosting
_COMMON_RISKS: list[RiskFactor] = [
    RiskFactor(
        category="reliability",
        description="GPU instance downtime or cold start delays",
        severity="medium",
        mitigation="Keep API as fallback; auto-failover on self-hosted timeout",
    ),
    RiskFactor(
        category="operational",
        description="Maintenance overhead: monitoring, updates, debugging",
        severity="medium",
        mitigation="Budget 4-8 hours/month; use health checks and alerting",
    ),
    RiskFactor(
        category="quality",
        description="Self-hosted model may not match API quality exactly",
        severity="medium",
        mitigation="Run A/B test with N=20 samples before full migration",
    ),
    RiskFactor(
        category="financial",
        description="GPU costs are fixed regardless of usage volume",
        severity="low",
        mitigation="Use serverless/on-demand pricing to match usage patterns",
    ),
]


class ProviderBenchmark:
    """Benchmarks providers and calculates self-hosting cost-effectiveness."""

    def __init__(
        self,
        settings: Settings,
        db_pool: AsyncConnectionPool,
        http_client: httpx.AsyncClient,
    ) -> None:
        self._settings = settings
        self._pool = db_pool
        self._http = http_client

    # ==================================================================
    # TTS Benchmark
    # ==================================================================

    async def benchmark_tts(
        self,
        text: str,
        providers: list[str],
        voice_id: str = "default",
    ) -> BenchmarkResult:
        """Run the same text through multiple TTS providers.

        Compares latency, cost, and saves audio samples for human A/B testing.
        """
        samples: list[BenchmarkSample] = []

        for name in providers:
            sample = await self._run_tts_sample(name, text, voice_id)
            samples.append(sample)

        comparisons = _build_comparisons(samples)
        successful = [s for s in samples if s.error is None]
        fastest = min(successful, key=lambda s: s.latency_ms).provider if successful else ""
        cheapest = min(successful, key=lambda s: s.cost_usd).provider if successful else ""

        result = BenchmarkResult(
            benchmark_type="tts",
            input_description=text[:100],
            providers=providers,
            samples=samples,
            comparisons=comparisons,
            fastest_provider=fastest,
            cheapest_provider=cheapest,
        )

        await logger.ainfo(
            "benchmark_tts_complete",
            providers=providers,
            fastest=fastest,
            cheapest=cheapest,
        )
        return result

    async def _run_tts_sample(
        self,
        provider_name: str,
        text: str,
        voice_id: str,
    ) -> BenchmarkSample:
        try:
            provider = ProviderFactory.get_tts_provider(
                provider_name,
                self._settings,
                self._http,
            )
            start = time.monotonic()
            result = await provider.generate(text, voice_id)
            latency = int((time.monotonic() - start) * 1000)

            return BenchmarkSample(
                provider=provider_name,
                latency_ms=latency,
                cost_usd=result.cost_usd,
                output_path=result.file_path,
                metadata={
                    "duration_seconds": result.duration_seconds,
                    "sample_rate": result.sample_rate,
                    "character_count": result.character_count,
                },
            )
        except Exception as exc:
            return BenchmarkSample(
                provider=provider_name,
                error=f"{type(exc).__name__}: {exc}",
            )

    # ==================================================================
    # Image Benchmark
    # ==================================================================

    async def benchmark_images(
        self,
        prompt: str,
        providers: list[str],
        width: int = 1920,
        height: int = 1080,
    ) -> BenchmarkResult:
        """Generate the same prompt on multiple image providers."""
        samples: list[BenchmarkSample] = []

        for name in providers:
            sample = await self._run_image_sample(name, prompt, width, height)
            samples.append(sample)

        comparisons = _build_comparisons(samples)
        successful = [s for s in samples if s.error is None]
        fastest = min(successful, key=lambda s: s.latency_ms).provider if successful else ""
        cheapest = min(successful, key=lambda s: s.cost_usd).provider if successful else ""

        return BenchmarkResult(
            benchmark_type="image",
            input_description=prompt[:100],
            providers=providers,
            samples=samples,
            comparisons=comparisons,
            fastest_provider=fastest,
            cheapest_provider=cheapest,
        )

    async def _run_image_sample(
        self,
        provider_name: str,
        prompt: str,
        width: int,
        height: int,
    ) -> BenchmarkSample:
        try:
            provider = ProviderFactory.get_image_provider(
                provider_name,
                self._settings,
                self._http,
            )
            start = time.monotonic()
            result = await provider.generate(prompt, width, height)
            latency = int((time.monotonic() - start) * 1000)

            return BenchmarkSample(
                provider=provider_name,
                latency_ms=latency,
                cost_usd=result.cost_usd,
                output_path=result.file_path,
                metadata={
                    "width": result.width,
                    "height": result.height,
                    "model": result.model,
                },
            )
        except Exception as exc:
            return BenchmarkSample(
                provider=provider_name,
                error=f"{type(exc).__name__}: {exc}",
            )

    # ==================================================================
    # Break-even analysis
    # ==================================================================

    async def calculate_break_even(
        self,
        current_provider: str,
        current_monthly_cost: Decimal,
        target_provider: str | None = None,
        current_volume: int = 0,
    ) -> BreakEvenAnalysis:
        """Calculate when self-hosting becomes cheaper than the API.

        Break-even formula:
          monthly_gpu_cost + maintenance_cost < current_api_cost

        Parameters
        ----------
        current_provider:
            Name of the current API provider (e.g., "fish_audio").
        current_monthly_cost:
            What you currently pay per month for this service.
        target_provider:
            Self-hosted alternative. Auto-detected if None.
        current_volume:
            Current monthly generation count (characters, images, etc.).
        """
        # Auto-detect target provider
        if target_provider is None:
            target_provider = _default_self_hosted(current_provider)

        # Get GPU cost estimate
        gpu = _GPU_PRESETS.get(target_provider, GPUCostEstimate())
        maintenance = MaintenanceCost()

        total_self_hosted = (
            gpu.monthly_gpu_cost_usd
            + gpu.monthly_storage_usd
            + gpu.monthly_bandwidth_usd
            + maintenance.monthly_cost_usd
        )
        monthly_savings = current_monthly_cost - total_self_hosted

        # Calculate break-even volume
        break_even_volume = 0
        api_unit = _API_UNIT_COSTS.get(current_provider)
        self_unit = _SELF_HOSTED_UNIT_COSTS.get(target_provider)
        if api_unit and self_unit and api_unit[1] > 0:
            # Fixed cost that must be covered by per-unit savings
            fixed_monthly = (
                gpu.monthly_gpu_cost_usd
                + gpu.monthly_storage_usd
                + gpu.monthly_bandwidth_usd
                + maintenance.monthly_cost_usd
            )
            per_unit_savings = api_unit[1] - self_unit[1]
            if per_unit_savings > 0:
                break_even_volume = int((fixed_monthly / per_unit_savings).to_integral_value())

        # Payback period
        setup_cost = Decimal("500")
        payback_months = 0
        if monthly_savings > 0:
            payback_months = int((setup_cost / monthly_savings).to_integral_value()) + 1

        # Determine recommendation
        recommendation: Literal["migrate", "wait", "not_recommended"]
        reasoning: str
        if monthly_savings <= 0:
            recommendation = "not_recommended"
            reasoning = (
                f"Self-hosting costs ${total_self_hosted}/month vs "
                f"${current_monthly_cost}/month API. No savings."
            )
        elif payback_months > 6:
            recommendation = "wait"
            reasoning = (
                f"Saves ${monthly_savings}/month but {payback_months}-month "
                f"payback. Wait for higher volume or lower GPU costs."
            )
        else:
            recommendation = "migrate"
            reasoning = (
                f"Saves ${monthly_savings}/month with {payback_months}-month "
                f"payback. Migration recommended."
            )

        risks = list(_COMMON_RISKS)
        if target_provider == "kokoro":
            risks.append(
                RiskFactor(
                    category="quality",
                    description="Kokoro 24kHz output is lower quality than Fish Audio 48kHz",
                    severity="high",
                    mitigation="Use only for secondary channels; keep Fish Audio for flagship",
                )
            )

        return BreakEvenAnalysis(
            current_provider=current_provider,
            target_provider=target_provider,
            current_monthly_cost_usd=current_monthly_cost,
            gpu_estimate=gpu,
            maintenance=maintenance,
            total_self_hosted_monthly_usd=total_self_hosted,
            monthly_savings_usd=monthly_savings,
            break_even_volume=break_even_volume,
            current_volume=current_volume,
            payback_period_months=payback_months,
            setup_cost_usd=setup_cost,
            risk_factors=risks,
            recommendation=recommendation,
            reasoning=reasoning,
        )

    # ==================================================================
    # Migration plan
    # ==================================================================

    async def generate_migration_plan(
        self,
        from_provider: str,
        to_provider: str,
    ) -> MigrationPlan:
        """Generate a step-by-step migration plan with rollback strategy."""
        steps = [
            MigrationStep(
                step_number=1,
                title="Deploy self-hosted model",
                description=(
                    f"Set up {to_provider} on GPU instance. "
                    f"Deploy Docker container with FastAPI wrapper. "
                    f"Verify health check endpoint responds."
                ),
                estimated_hours=Decimal("4"),
                rollback_plan="Terminate GPU instance; no cost impact.",
            ),
            MigrationStep(
                step_number=2,
                title="Run benchmark comparison",
                description=(
                    f"Generate N=20 identical samples on both {from_provider} "
                    f"and {to_provider}. Compare latency, cost, and save "
                    f"output files for human quality review."
                ),
                estimated_hours=Decimal("2"),
                dependencies=[1],
                rollback_plan="No changes to production; benchmark is read-only.",
            ),
            MigrationStep(
                step_number=3,
                title="Human quality review",
                description=(
                    "Blind A/B test: present 20 sample pairs to 2-3 reviewers. "
                    "Score on a 1-5 scale. Require self-hosted average >= 3.5 "
                    "and no sample below 2.0 to proceed."
                ),
                estimated_hours=Decimal("3"),
                dependencies=[2],
                rollback_plan="If quality fails, stop migration; keep API.",
            ),
            MigrationStep(
                step_number=4,
                title="Route 10% traffic to self-hosted",
                description=(
                    f"Configure provider routing to send 10% of requests to "
                    f"{to_provider}. Monitor error rates, latency p50/p99, "
                    f"and cost per generation for 1 week."
                ),
                estimated_hours=Decimal("2"),
                dependencies=[3],
                rollback_plan=(
                    f"Set routing back to 100% {from_provider}. "
                    f"Automatic via failover if self-hosted error rate > 5%."
                ),
            ),
            MigrationStep(
                step_number=5,
                title="Ramp to 50% traffic",
                description=(
                    "If 10% routing shows acceptable quality and reliability "
                    "for 1 week, increase to 50%. Monitor for another week."
                ),
                estimated_hours=Decimal("1"),
                dependencies=[4],
                rollback_plan=f"Reduce back to 10% or 0% {to_provider}.",
            ),
            MigrationStep(
                step_number=6,
                title="Full migration to 100%",
                description=(
                    f"Route all traffic to {to_provider}. Keep {from_provider} "
                    f"configured as automatic fallback (failover on timeout or "
                    f"5xx errors). Monitor for 2 weeks."
                ),
                estimated_hours=Decimal("1"),
                dependencies=[5],
                rollback_plan=(
                    f"Auto-failover to {from_provider} on any self-hosted failure. "
                    f"Manual rollback: set routing to 100% {from_provider}."
                ),
            ),
            MigrationStep(
                step_number=7,
                title="Decommission API fallback (optional)",
                description=(
                    f"After 1 month of stable self-hosted operation, optionally "
                    f"remove {from_provider} API key to stop subscription charges. "
                    f"Keep the provider code for emergency re-enablement."
                ),
                estimated_hours=Decimal("1"),
                dependencies=[6],
                rollback_plan=f"Re-add {from_provider} API key and set as primary.",
            ),
        ]

        total_hours = sum((s.estimated_hours for s in steps), Decimal("0"))

        return MigrationPlan(
            from_provider=from_provider,
            to_provider=to_provider,
            steps=steps,
            total_estimated_hours=total_hours,
            estimated_calendar_days=21,  # 3 weeks with monitoring periods
            rollback_strategy=(
                f"At any step, revert to {from_provider} by setting "
                f"the provider config back to '{from_provider}'. The abstraction "
                f"layer makes this a config-only change with zero code changes."
            ),
            success_criteria=[
                "Self-hosted latency p99 < 2x API latency",
                "Error rate < 1% over 1 week",
                "Human quality score >= 3.5/5.0 in blind test",
                "Monthly cost < current API cost (excluding setup)",
                "No pipeline failures attributable to provider change",
            ],
        )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _build_comparisons(samples: list[BenchmarkSample]) -> list[ProviderComparison]:
    """Build pairwise comparisons between all successful samples."""
    successful = [s for s in samples if s.error is None]
    comparisons: list[ProviderComparison] = []

    for i, a in enumerate(successful):
        for b in successful[i + 1 :]:
            latency_delta = a.latency_ms - b.latency_ms
            cost_delta = a.cost_usd - b.cost_usd
            comparisons.append(
                ProviderComparison(
                    provider_a=a.provider,
                    provider_b=b.provider,
                    sample_a=a,
                    sample_b=b,
                    latency_delta_ms=latency_delta,
                    cost_delta_usd=cost_delta,
                    latency_winner=a.provider if latency_delta < 0 else b.provider,
                    cost_winner=a.provider if cost_delta < 0 else b.provider,
                )
            )

    return comparisons


def _default_self_hosted(api_provider: str) -> str:
    """Map an API provider to its default self-hosted alternative."""
    defaults = {
        "fish_audio": "chatterbox",
        "fal_ai": "local_flux",
        "epidemic_sound_library": "ace_step",
    }
    return defaults.get(api_provider, "")
