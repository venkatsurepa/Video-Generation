"""Models for provider benchmarking and self-hosting cost analysis.

Used by the benchmark service to compare API vs self-hosted providers
and calculate break-even points for migration decisions.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Benchmark results
# ---------------------------------------------------------------------------


class BenchmarkSample(BaseModel):
    """A single benchmark run for one provider."""

    provider: str
    latency_ms: int = 0
    cost_usd: Decimal = Decimal("0")
    output_path: str = Field(default="", description="Path to generated output file")
    error: str | None = None
    metadata: dict[str, object] = Field(default_factory=dict)


class ProviderComparison(BaseModel):
    """Side-by-side comparison of two providers on the same input."""

    provider_a: str
    provider_b: str
    sample_a: BenchmarkSample
    sample_b: BenchmarkSample
    latency_delta_ms: int = 0
    cost_delta_usd: Decimal = Decimal("0")
    latency_winner: str = ""
    cost_winner: str = ""


class BenchmarkResult(BaseModel):
    """Aggregate result of benchmarking N providers on the same input."""

    benchmark_type: Literal["tts", "image", "music", "llm"]
    input_description: str = Field(description="What was benchmarked (text snippet, prompt, etc.)")
    providers: list[str]
    samples: list[BenchmarkSample]
    comparisons: list[ProviderComparison] = Field(default_factory=list)
    fastest_provider: str = ""
    cheapest_provider: str = ""
    timestamp: datetime = Field(default_factory=datetime.utcnow)


# ---------------------------------------------------------------------------
# Break-even analysis
# ---------------------------------------------------------------------------


class GPUCostEstimate(BaseModel):
    """Cost breakdown for a self-hosted GPU deployment."""

    provider: Literal["runpod", "vast_ai", "dedicated"] = "vast_ai"
    gpu_model: str = "RTX 4090"
    hourly_rate_usd: Decimal = Decimal("0.50")
    monthly_hours: Decimal = Field(
        default=Decimal("730"),
        description="Hours/month (730 = always-on, less for on-demand)",
    )
    monthly_gpu_cost_usd: Decimal = Decimal("0")
    monthly_storage_usd: Decimal = Decimal("10")
    monthly_bandwidth_usd: Decimal = Decimal("5")

    def model_post_init(self, __context: object) -> None:
        if self.monthly_gpu_cost_usd == 0:
            self.monthly_gpu_cost_usd = (self.hourly_rate_usd * self.monthly_hours).quantize(
                Decimal("0.01")
            )


class MaintenanceCost(BaseModel):
    """Implicit maintenance overhead for self-hosting."""

    hours_per_month: Decimal = Field(
        default=Decimal("6"),
        description="Estimated maintenance hours (monitoring, updates, debugging)",
    )
    hourly_rate_usd: Decimal = Field(
        default=Decimal("100"),
        description="Implicit cost of engineer time",
    )
    monthly_cost_usd: Decimal = Decimal("0")

    def model_post_init(self, __context: object) -> None:
        if self.monthly_cost_usd == 0:
            self.monthly_cost_usd = (self.hours_per_month * self.hourly_rate_usd).quantize(
                Decimal("0.01")
            )


class RiskFactor(BaseModel):
    """A risk associated with self-hosting migration."""

    category: Literal["quality", "reliability", "operational", "financial"]
    description: str
    severity: Literal["low", "medium", "high"]
    mitigation: str = ""


class BreakEvenAnalysis(BaseModel):
    """Full break-even analysis for migrating from API to self-hosted.

    Based on the formula:
    monthly_gpu_cost + maintenance_cost < current_api_cost
    """

    current_provider: str
    target_provider: str
    current_monthly_cost_usd: Decimal
    gpu_estimate: GPUCostEstimate
    maintenance: MaintenanceCost
    total_self_hosted_monthly_usd: Decimal = Decimal("0")
    monthly_savings_usd: Decimal = Decimal("0")
    break_even_volume: int = Field(
        default=0,
        description="Monthly generation count where self-hosting becomes cheaper",
    )
    current_volume: int = Field(default=0, description="Current monthly generation count")
    payback_period_months: int = Field(
        default=0,
        description="Months until cumulative savings cover setup cost",
    )
    setup_cost_usd: Decimal = Field(
        default=Decimal("500"),
        description="One-time setup cost (deployment, testing, integration)",
    )
    risk_factors: list[RiskFactor] = Field(default_factory=list)
    recommendation: Literal["migrate", "wait", "not_recommended"] = "wait"
    reasoning: str = ""
    timestamp: datetime = Field(default_factory=datetime.utcnow)


# ---------------------------------------------------------------------------
# Migration plan
# ---------------------------------------------------------------------------


class MigrationStep(BaseModel):
    """A single step in a provider migration plan."""

    step_number: int
    title: str
    description: str
    estimated_hours: Decimal = Decimal("0")
    dependencies: list[int] = Field(
        default_factory=list,
        description="Step numbers this depends on",
    )
    rollback_plan: str = ""


class MigrationPlan(BaseModel):
    """Step-by-step plan for migrating from one provider to another."""

    from_provider: str
    to_provider: str
    steps: list[MigrationStep]
    total_estimated_hours: Decimal = Decimal("0")
    estimated_calendar_days: int = 14
    rollback_strategy: str = ""
    success_criteria: list[str] = Field(default_factory=list)
    timestamp: datetime = Field(default_factory=datetime.utcnow)
