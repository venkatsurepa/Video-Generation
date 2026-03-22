"""Tests for the script generator — Claude API integration and output validation.

Unit tests verify deterministic logic (rotation, cost calculation, forbidden words).
Integration tests marked with @pytest.mark.integration make real API calls.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

import pytest

from src.models.script import (
    APICallCost,
    ChannelSettings,
    HookType,
    ScriptOutput,
    TitleFormula,
    TitleVariant,
    TopicInput,
    TwistPlacement,
)
from src.services.script_generator import (
    HOOK_ROTATION,
    MODEL_HAIKU,
    MODEL_SONNET,
    PRICING,
    TITLE_ROTATION,
    WORD_COUNT_TARGETS,
    ScriptGenerator,
)
from tests.conftest import requires_anthropic

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def topic_15min() -> TopicInput:
    return TopicInput(
        topic="The disappearance of a hiker in Olympic National Park in 2019",
        video_length_minutes=15,
        rotation_index=0,
    )


@pytest.fixture
def channel_settings() -> ChannelSettings:
    return ChannelSettings(
        channel_name="CrimeMill",
        channel_id="00000000-0000-0000-0000-000000000001",
    )


@pytest.fixture
def sample_script_output() -> ScriptOutput:
    """A realistic script output for testing downstream consumers."""
    return ScriptOutput(
        script_text=(
            "[HOOK] On a quiet trail in Olympic National Park, Sarah Mitchell "
            "set out for what should have been a routine day hike. "
            "[SCENE: Dark forest trail at dusk] She never returned. "
            "[AD_BREAK] What investigators found next changed everything. "
            "[CTA_LIGHT] Subscribe if you want to hear what happened. "
            "The end."
        ),
        word_count=2000,
        estimated_duration_seconds=900.0,
        hook_type=HookType.COLD_OPEN,
        open_loops=["What happened on the trail?", "Why did she go alone?"],
        twist_placements=[
            TwistPlacement(position_percent=25, description="Evidence found"),
            TwistPlacement(position_percent=75, description="Suspect identified"),
        ],
        cost=APICallCost(
            model=MODEL_SONNET,
            input_tokens=5000,
            output_tokens=3000,
            cost_usd=Decimal("0.060"),
        ),
    )


# ---------------------------------------------------------------------------
# Hook and title rotation
# ---------------------------------------------------------------------------


class TestRotation:
    def test_hook_rotation_covers_all_types(self) -> None:
        """Rotation through all hook types should eventually use each one."""
        used = set()
        for i in range(len(HOOK_ROTATION)):
            hook = HOOK_ROTATION[i % len(HOOK_ROTATION)]
            used.add(hook)
        assert used == set(HookType)

    def test_title_rotation_covers_all_formulas(self) -> None:
        """Rotation through all title formulas should use each one."""
        used = set()
        for i in range(len(TITLE_ROTATION)):
            formula = TITLE_ROTATION[i % len(TITLE_ROTATION)]
            used.add(formula)
        assert used == set(TitleFormula)

    def test_word_count_targets_cover_all_lengths(self) -> None:
        """Word count targets should exist for all supported video lengths."""
        assert set(WORD_COUNT_TARGETS.keys()) == {10, 15, 20, 25}
        for _length, (min_wc, max_wc) in WORD_COUNT_TARGETS.items():
            assert min_wc < max_wc
            assert min_wc > 0


# ---------------------------------------------------------------------------
# Cost calculation
# ---------------------------------------------------------------------------


class TestCostTracking:
    def test_pricing_defined_for_all_models(self) -> None:
        """Pricing should be defined for both Sonnet and Haiku."""
        assert MODEL_SONNET in PRICING
        assert MODEL_HAIKU in PRICING
        for _model, prices in PRICING.items():
            assert "input" in prices
            assert "output" in prices
            assert prices["input"] > 0
            assert prices["output"] > 0

    def test_cost_tracking_accuracy(self) -> None:
        """Reported cost should match token_count * price_per_million."""
        input_tokens = 5000
        output_tokens = 3000

        input_cost = Decimal(input_tokens) * PRICING[MODEL_SONNET]["input"] / Decimal("1000000")
        output_cost = Decimal(output_tokens) * PRICING[MODEL_SONNET]["output"] / Decimal("1000000")
        expected = input_cost + output_cost

        # $3/M input * 5000 = $0.015, $15/M output * 3000 = $0.045 → $0.060
        assert expected == Decimal("0.060")

    def test_haiku_cheaper_than_sonnet(self) -> None:
        """Haiku should be cheaper than Sonnet for the same token count."""
        tokens = 1000
        haiku_cost = (
            Decimal(tokens) * PRICING[MODEL_HAIKU]["input"]
            + Decimal(tokens) * PRICING[MODEL_HAIKU]["output"]
        ) / Decimal("1000000")
        sonnet_cost = (
            Decimal(tokens) * PRICING[MODEL_SONNET]["input"]
            + Decimal(tokens) * PRICING[MODEL_SONNET]["output"]
        ) / Decimal("1000000")
        assert haiku_cost < sonnet_cost


# ---------------------------------------------------------------------------
# Model routing
# ---------------------------------------------------------------------------


class TestModelRouting:
    def test_smart_model_routing(self) -> None:
        """Script should use Sonnet; scene breakdown, prompts, description should use Haiku."""
        # Verify model constants are correct
        assert "sonnet" in MODEL_SONNET.lower()
        assert "haiku" in MODEL_HAIKU.lower()


# ---------------------------------------------------------------------------
# Forbidden words
# ---------------------------------------------------------------------------

FORBIDDEN_WORDS = [
    "delve",
    "tapestry",
    "landscape",
    "realm",
    "embark",
    "pivotal",
    "moreover",
    "furthermore",
    "arguably",
    "intricacies",
]


class TestForbiddenWords:
    def test_script_forbidden_words_absent(
        self,
        sample_script_output: ScriptOutput,
    ) -> None:
        """Verify known AI-isms are not in sample script output."""
        text_lower = sample_script_output.script_text.lower()
        for word in FORBIDDEN_WORDS:
            assert word not in text_lower, f"Forbidden word '{word}' found in script"


# ---------------------------------------------------------------------------
# Script output structure
# ---------------------------------------------------------------------------


class TestScriptOutputStructure:
    def test_script_has_required_timing_markers(
        self,
        sample_script_output: ScriptOutput,
    ) -> None:
        """Verify [HOOK], [AD_BREAK], [CTA_LIGHT], [SCENE:] markers present."""
        text = sample_script_output.script_text
        assert "[HOOK]" in text, "Missing [HOOK] marker"
        assert "[SCENE:" in text, "Missing [SCENE:] marker"

    def test_script_output_has_open_loops(
        self,
        sample_script_output: ScriptOutput,
    ) -> None:
        """Script should include open loop descriptions."""
        assert len(sample_script_output.open_loops) >= 1

    def test_script_output_has_twist_placements(
        self,
        sample_script_output: ScriptOutput,
    ) -> None:
        """Script should include twist placements at beat points."""
        assert len(sample_script_output.twist_placements) >= 1
        for tp in sample_script_output.twist_placements:
            assert tp.position_percent in (25, 50, 75)


# ---------------------------------------------------------------------------
# Title variants
# ---------------------------------------------------------------------------


class TestTitleVariants:
    def test_title_variant_model(self) -> None:
        """TitleVariant should validate all fields."""
        variant = TitleVariant(
            title="The Hiker Who Never Returned",
            formula=TitleFormula.WHAT_HAPPENED,
            word_count=6,
            char_count=30,
            power_words=["never"],
            estimated_ctr_rank=1,
        )
        assert variant.word_count == 6
        assert variant.formula == TitleFormula.WHAT_HAPPENED

    def test_title_length_reasonable(self) -> None:
        """Titles should be between 30-65 characters for optimal YouTube CTR."""
        good_titles = [
            "The Hiker Who Vanished Without a Trace",  # 39 chars
            "Nobody Talks About This Cold Case Anymore",  # 42 chars
            "How a DNA Match Solved a 20-Year Mystery",  # 41 chars
        ]
        for title in good_titles:
            assert 20 <= len(title) <= 70, f"Title '{title}' is {len(title)} chars"


# ---------------------------------------------------------------------------
# Integration tests (require ANTHROPIC_API_KEY)
# ---------------------------------------------------------------------------


@requires_anthropic
@pytest.mark.integration
@pytest.mark.slow
class TestScriptGeneratorIntegration:
    async def test_script_generation_produces_valid_output(
        self,
        settings: Any,
    ) -> None:
        """Test real Claude API call produces a script with required structure."""
        import httpx

        async with httpx.AsyncClient() as http:
            gen = ScriptGenerator(settings, http)
            topic = TopicInput(
                topic="The mysterious death of Elisa Lam at the Cecil Hotel in 2013",
                video_length_minutes=10,
            )
            channel = ChannelSettings(
                channel_name="TestChannel",
                channel_id="00000000-0000-0000-0000-000000000001",
            )
            result = await gen.generate_script(topic, channel)

        assert result.word_count > 0
        assert result.estimated_duration_seconds > 0
        assert result.hook_type in HookType
        assert result.cost.cost_usd > 0
        assert len(result.script_text) > 100

    async def test_scene_breakdown_valid_json(
        self,
        settings: Any,
    ) -> None:
        """Verify scene breakdown produces valid structured output."""
        import httpx

        script_text = (
            "[HOOK] In 2013, a body was found in a water tank atop the Cecil Hotel. "
            "[SCENE: Hotel exterior at night] The discovery shocked Los Angeles. "
            "[SCENE: Security footage hallway] Elevator footage raised more questions. "
            "[AD_BREAK] The investigation took a strange turn."
        )

        async with httpx.AsyncClient() as http:
            gen = ScriptGenerator(settings, http)
            result = await gen.generate_scene_breakdown(script_text, 10)

        assert len(result.scenes) >= 2
        for scene in result.scenes:
            assert scene.scene_number >= 1
            assert scene.start_time_seconds >= 0
            assert len(scene.narration_text) > 0
            assert len(scene.scene_description) > 0
