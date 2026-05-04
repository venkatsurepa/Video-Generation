"""Unit tests for the travel-safety generator and niche router."""
from __future__ import annotations

from decimal import Decimal
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.services.niche_router import (
    ALLOWED_NICHES,
    NicheRouter,
    is_travel_niche,
    normalize_niche,
)
from src.services.prompts import get_prompts_for_niche
from src.services.prompts.travel_prompts import (
    TRANSFORM_SYSTEM_PROMPT,
)
from src.services.rhyo_agent_client import RhyoAgentClient

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "hyderabad_banjara_hills_rhyo.md"


# ---------------------------------------------------------------------------
# Niche router
# ---------------------------------------------------------------------------


def test_normalize_niche_known() -> None:
    assert normalize_niche("travel_safety") == "travel_safety"
    assert normalize_niche("financial_crime") == "financial_crime"


def test_normalize_niche_unknown_falls_back() -> None:
    assert normalize_niche(None) == "financial_crime"
    assert normalize_niche("") == "financial_crime"
    assert normalize_niche("nonsense") == "financial_crime"


def test_is_travel_niche() -> None:
    assert is_travel_niche("travel_safety") is True
    assert is_travel_niche("financial_crime") is False
    assert is_travel_niche(None) is False


def test_allowed_niches_includes_travel_safety() -> None:
    assert "travel_safety" in ALLOWED_NICHES
    assert "financial_crime" in ALLOWED_NICHES


def test_router_routes_to_travel_prompts() -> None:
    router = NicheRouter("travel_safety")
    assert router.is_travel is True
    assert router.prompts.NICHE == "travel_safety"


def test_router_routes_to_crime_prompts() -> None:
    router = NicheRouter("financial_crime")
    assert router.is_travel is False
    assert router.prompts.NICHE == "financial_crime"


def test_router_unknown_niche_falls_back_to_crime() -> None:
    router = NicheRouter("does_not_exist")
    assert router.niche == "financial_crime"
    assert router.is_travel is False


def test_get_prompts_for_niche() -> None:
    crime = get_prompts_for_niche("financial_crime")
    travel = get_prompts_for_niche("travel_safety")
    assert crime.NICHE == "financial_crime"
    assert travel.NICHE == "travel_safety"
    # crime re-exports must include the existing constants
    assert hasattr(crime, "SCRIPT_SYSTEM_PROMPT")
    assert hasattr(crime, "DESCRIPTION_SYSTEM_PROMPT")
    # travel prompts have the transform prompt
    assert hasattr(travel, "TRANSFORM_SYSTEM_PROMPT")


def test_travel_transform_prompt_has_voice_rules() -> None:
    # The prompt must encode the warm-tone rules so future edits don't drift
    assert "well-traveled friend" in TRANSFORM_SYSTEM_PROMPT
    assert "DO NOT INVENT FACTS" in TRANSFORM_SYSTEM_PROMPT
    assert "Rhyo Security Solutions" in TRANSFORM_SYSTEM_PROMPT or "rhyo.com" in TRANSFORM_SYSTEM_PROMPT


# ---------------------------------------------------------------------------
# Rhyo client stub
# ---------------------------------------------------------------------------


def test_rhyo_report_from_markdown() -> None:
    md = FIXTURE_PATH.read_text(encoding="utf-8")
    report = RhyoAgentClient.from_markdown(
        md,
        destination_label="Banjara Hills, Hyderabad, India",
        country_code="in",
        city="Hyderabad",
        region="Telangana",
    )
    assert report.country_code == "IN"  # uppercased
    assert report.city == "Hyderabad"
    assert report.source == "fixture"
    assert report.word_count > 100


@pytest.mark.asyncio
async def test_rhyo_live_fetch_not_implemented() -> None:
    settings = MagicMock()
    settings.anthropic.api_key = "test"
    http = AsyncMock()
    client = RhyoAgentClient(settings, http)
    with pytest.raises(NotImplementedError):
        await client.fetch_report(
            destination_label="x", country_code="IN", city="x"
        )


# ---------------------------------------------------------------------------
# Bare-name model aliases (added so audit-style imports without the *Base
# suffix resolve)
# ---------------------------------------------------------------------------


def test_video_destination_bare_alias_importable() -> None:
    from src.models.video_destination import VideoDestination, VideoDestinationBase

    assert VideoDestination is VideoDestinationBase


def test_travel_advisory_bare_alias_importable() -> None:
    from src.models.travel_advisory import TravelAdvisory, TravelAdvisoryBase

    assert TravelAdvisory is TravelAdvisoryBase


def test_partner_app_metric_bare_alias_importable() -> None:
    from src.models.partner_app_metric import PartnerAppMetric, PartnerAppMetricBase

    assert PartnerAppMetric is PartnerAppMetricBase


# ---------------------------------------------------------------------------
# Tolerant JSON parser (used by the multi-call generator's Haiku stages —
# previously covered indirectly by the legacy _strip_json_fences tests)
# ---------------------------------------------------------------------------

from src.services.script_generators.travel_safety_generator import (  # noqa: E402
    _tolerant_json_parse,
)


def test_tolerant_json_parse_handles_bare_object() -> None:
    assert _tolerant_json_parse('{"a": 1}') == {"a": 1}


def test_tolerant_json_parse_handles_fenced_object() -> None:
    assert _tolerant_json_parse('```json\n{"a": 1}\n```') == {"a": 1}


def test_tolerant_json_parse_handles_prose_prefix() -> None:
    assert _tolerant_json_parse('Here you go:\n{"a": 1}\n') == {"a": 1}


def test_tolerant_json_parse_returns_none_on_garbage() -> None:
    assert _tolerant_json_parse("this is not json at all") is None


# ---------------------------------------------------------------------------
# Multi-call generator: TravelSafetyScriptGenerator
# ---------------------------------------------------------------------------

from src.services.prompts.travel_prompts import (  # noqa: E402
    SCRIPT_SYSTEM_PROMPT as TS_SCRIPT_SYSTEM_PROMPT,
)
from src.services.script_generators.travel_safety_generator import (  # noqa: E402
    RhyoReport,
    TravelSafetyScriptGenerator,
    parse_rhyo_report,
)
from src.services.script_generators.travel_safety_generator import (  # noqa: E402
    VideoDestination as TSVideoDestination,
)

REPORTS_DIR = Path(__file__).parent.parent / "fixtures" / "rhyo_reports"
BANJARA_PATH = REPORTS_DIR / "hyderabad_banjara_hills.md"
OLD_CITY_PATH = REPORTS_DIR / "hyderabad_old_city.md"
SAMPLE_TRAVEL_SCRIPT_PATH = Path(__file__).parent / "fixtures" / "sample_travel_script.txt"


def test_load_rhyo_report_parses_banjara_hills() -> None:
    report = parse_rhyo_report(BANJARA_PATH)
    assert isinstance(report, RhyoReport)
    assert "Banjara Hills" in report.location_name
    assert report.country_code == "IN"
    assert report.region == "Telangana"
    assert report.city == "Hyderabad"
    assert report.overall_day_score == pytest.approx(65.1)
    assert report.overall_night_score == pytest.approx(53.1)
    assert report.band == "Guarded"
    assert report.confidence == pytest.approx(100.0)
    assert len(report.sections) >= 9
    assert "Banjara Hills" in report.raw_markdown
    assert report.coordinates is not None
    assert report.coordinates[0] == pytest.approx(17.4156)
    # Top dominant risks should include the highest-value risk columns
    assert "crime_risk" in report.dominant_risks


def test_load_rhyo_report_old_city_has_warnings() -> None:
    report = parse_rhyo_report(OLD_CITY_PATH)
    # Old City has confidence=1 + lighting / fallback caveats preserved
    assert report.country_code == "IN"
    assert len(report.data_quality_warnings) > 0
    # Confidence should be parsed as 1 (the floor)
    assert report.confidence is not None
    assert report.confidence <= 5  # confidence floor


def test_select_video_format_returns_safety_briefing_for_banjara_hills() -> None:
    report = parse_rhyo_report(BANJARA_PATH)
    # Banjara Hills: day=65.1, band=Guarded -> safety_briefing per spec
    assert TravelSafetyScriptGenerator.select_video_format(report) == "safety_briefing"


def test_select_video_format_old_city_returns_crisis_response() -> None:
    # Old City has confidence=1 (well below the 30 threshold) so it
    # routes to crisis_response. Documenting the actual return here per
    # the task spec — either safety_briefing or crisis_response was
    # acceptable; we picked the confidence-floor branch.
    report = parse_rhyo_report(OLD_CITY_PATH)
    assert TravelSafetyScriptGenerator.select_video_format(report) == "crisis_response"


def test_extract_destinations_banjara_hills() -> None:
    report = parse_rhyo_report(BANJARA_PATH)
    dests = TravelSafetyScriptGenerator.extract_destinations(
        report, "ignored script", "safety_briefing"
    )
    assert len(dests) >= 1
    primary = dests[0]
    assert isinstance(primary, TSVideoDestination)
    assert primary.country_code == "IN"
    assert primary.city == "Hyderabad"
    assert primary.region_or_state == "Telangana"
    assert primary.relevance == "primary"
    # POI should reference Banjara Hills, or the format tag should at
    # minimum carry the safety_briefing label
    poi_match = "Banjara Hills" in (primary.poi_name or "")
    tag_match = "safety_briefing" in primary.safepath_tags
    assert poi_match or tag_match


def _make_anthropic_response_mock(text: str) -> MagicMock:
    """Build a mock anthropic.AsyncMessages.create response."""
    response = MagicMock()
    content = MagicMock()
    content.text = text
    response.content = [content]
    usage = MagicMock()
    usage.input_tokens = 1000
    usage.output_tokens = 2500
    usage.cache_creation_input_tokens = 0
    usage.cache_read_input_tokens = 0
    response.usage = usage
    return response


@pytest.mark.asyncio
async def test_generate_script_with_mocked_anthropic() -> None:
    """End-to-end script call with a mocked Anthropic client."""
    sample_script = SAMPLE_TRAVEL_SCRIPT_PATH.read_text(encoding="utf-8")

    settings = MagicMock()
    settings.anthropic.api_key = "test-key"
    http = AsyncMock()

    mock_client = MagicMock()
    mock_client.messages = MagicMock()
    mock_client.messages.create = AsyncMock(
        return_value=_make_anthropic_response_mock(sample_script)
    )

    gen = TravelSafetyScriptGenerator(settings, http, client=mock_client)
    report = parse_rhyo_report(BANJARA_PATH)
    script_text, cost = await gen.generate_script(report, "safety_briefing")

    # The mocked call was made
    assert mock_client.messages.create.await_count == 1
    call_kwargs = mock_client.messages.create.await_args.kwargs

    # System prompt is the travel SCRIPT_SYSTEM_PROMPT
    system_payload = call_kwargs["system"]
    assert isinstance(system_payload, list)
    assert system_payload[0]["text"] == TS_SCRIPT_SYSTEM_PROMPT

    # User message includes the report markdown verbatim
    user_msg = call_kwargs["messages"][0]["content"]
    assert "FORMAT: safety_briefing" in user_msg
    assert "Banjara Hills" in user_msg
    assert "RHYO Safety Intelligence Report" in user_msg

    # Returned script matches the mock body
    assert script_text.strip() == sample_script.strip()
    assert cost > Decimal("0")


def test_script_system_prompt_explicitly_bans_crime_doc_tokens() -> None:
    """The travel script system prompt MUST explicitly ban the crime-doc
    voice tokens (the words appear in the prompt as forbidden examples)."""
    must_ban = ("chilling", "shocking", "in a stunning turn of events")
    lowered = TS_SCRIPT_SYSTEM_PROMPT.lower()
    for token in must_ban:
        assert token in lowered, f"prompt must explicitly forbid {token!r}"
    # And the prompt must include the forbidden-list section header so
    # the model knows it's a ban list, not a usage list.
    assert "forbidden" in lowered or "do not use" in lowered or "never" in lowered


@pytest.mark.asyncio
async def test_sample_travel_script_fixture_is_clean() -> None:
    """The sample script fixture itself must not contain forbidden tokens
    (so the generator test harness models the right voice)."""
    text = SAMPLE_TRAVEL_SCRIPT_PATH.read_text(encoding="utf-8").lower()
    forbidden = (
        "chilling",
        "shocking",
        "in a stunning turn of events",
        "authorities allege",
        "what you're about to see",
        "you won't believe",
    )
    for token in forbidden:
        assert token not in text, f"fixture script contains forbidden token: {token}"
    # And it should sound like the warm voice
    assert " you " in f" {text} " or text.startswith("you ")
    assert " we " in f" {text} "
    assert "street level" in text
    assert "banjara hills" in text


def test_build_assembled_prompts_returns_all_stages() -> None:
    settings = MagicMock()
    settings.anthropic.api_key = "test-key"
    http = AsyncMock()
    gen = TravelSafetyScriptGenerator(settings, http, client=MagicMock())
    out = gen.build_assembled_prompts(BANJARA_PATH)
    expected_stages = {
        "format",
        "script",
        "scene_breakdown",
        "image_prompts",
        "title",
        "description",
    }
    assert expected_stages.issubset(set(out.keys()))
    assert out["format"] == "safety_briefing"
    assert "RHYO Safety Intelligence Report" in out["script"]
    assert "--- USER ---" in out["script"]
