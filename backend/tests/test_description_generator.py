"""Tests for the YouTube description generator.

All tests are deterministic — no API calls needed. Verifies SEO structure,
legal compliance (FTC, Amazon Associates, AI disclosure), byte limits,
and chapter formatting.
"""

from __future__ import annotations

import uuid
from datetime import date
from typing import TYPE_CHECKING

import pytest

from src.config import Settings
from src.models.description import (
    AffiliateConfig,
    ChannelLinks,
    DescriptionInput,
    SourceCitation,
)
from src.services.description_generator import (
    SAFE_MAX_BYTES,
    YOUTUBE_MAX_BYTES,
    DescriptionGenerator,
)

if TYPE_CHECKING:
    from src.models.script import SceneBreakdown


@pytest.fixture
def generator() -> DescriptionGenerator:
    return DescriptionGenerator(Settings())


@pytest.fixture
def basic_input(sample_scenes: list[SceneBreakdown]) -> DescriptionInput:
    return DescriptionInput(
        video_id=uuid.uuid4(),
        title="The Olympic Park Disappearance",
        case_summary=(
            "In 2019, experienced hiker Sarah Mitchell vanished during a solo "
            "trek through Olympic National Park. Search teams found her abandoned "
            "campsite with disturbing signs of a struggle. Three years later, "
            "a breakthrough DNA match connected the case to a serial predator."
        ),
        scenes=sample_scenes,
        sources=[
            SourceCitation(
                title="FBI Missing Persons Report",
                source_type="government_report",
                url="https://example.com/fbi-report",
                publication_date=date(2019, 8, 15),
                timestamp_reference="2:30",
            ),
            SourceCitation(
                title="Seattle Times Investigation",
                source_type="news_article",
                url="https://example.com/seattle-times",
            ),
        ],
        affiliate_config=AffiliateConfig(
            vpn_link="https://nordvpn.com/crimemill",
            audible_link="https://audible.com/crimemill",
            amazon_tag="crimemill-20",
            geniuslink_base="https://geni.us/crimemill",
        ),
        channel_links=ChannelLinks(
            subscribe_url="https://youtube.com/c/crimemill?sub_confirmation=1",
            discord_invite="https://discord.gg/crimemill",
        ),
        hashtags=["TrueCrime", "ColdCase", "OlympicPark"],
        related_book_title="The Lost Hiker",
        related_book_asin="B08XYZ1234",
    )


class TestByteLimit:
    def test_description_under_5000_bytes(
        self,
        generator: DescriptionGenerator,
        basic_input: DescriptionInput,
    ) -> None:
        """Description must not exceed YouTube's 5,000-byte limit."""
        result = generator.generate_description(basic_input)
        byte_count = len(result.encode("utf-8"))
        assert byte_count <= YOUTUBE_MAX_BYTES, (
            f"Description is {byte_count} bytes, exceeds {YOUTUBE_MAX_BYTES}"
        )

    def test_description_under_safe_limit(
        self,
        generator: DescriptionGenerator,
        basic_input: DescriptionInput,
    ) -> None:
        """Description should stay under the 4,900-byte safe limit."""
        result = generator.generate_description(basic_input)
        byte_count = len(result.encode("utf-8"))
        assert byte_count <= SAFE_MAX_BYTES

    def test_truncation_preserves_hook_line(
        self,
        generator: DescriptionGenerator,
    ) -> None:
        """When truncated, the hook line (first line) must survive."""
        # Create an input with a massive summary to force truncation
        huge_summary = "A " * 3000
        input_data = DescriptionInput(
            video_id=uuid.uuid4(),
            title="Test",
            case_summary=huge_summary,
            scenes=[],
            hashtags=["Test"] * 5,
        )
        result = generator.generate_description(input_data)

        byte_count = len(result.encode("utf-8"))
        assert byte_count <= SAFE_MAX_BYTES
        # First line should still be present
        assert len(result.split("\n")[0]) > 0


class TestFTCCompliance:
    def test_ftc_disclosure_before_affiliate_links(
        self,
        generator: DescriptionGenerator,
        basic_input: DescriptionInput,
    ) -> None:
        """FTC disclosure must appear BEFORE any affiliate links."""
        result = generator.generate_description(basic_input)

        ftc_pos = result.find("FTC DISCLOSURE")
        vpn_pos = result.find("nordvpn.com")
        audible_pos = result.find("audible.com")

        assert ftc_pos != -1, "FTC disclosure missing"
        if vpn_pos != -1:
            assert ftc_pos < vpn_pos, "FTC disclosure must come before VPN link"
        if audible_pos != -1:
            assert ftc_pos < audible_pos, "FTC disclosure must come before Audible link"

    def test_amazon_associate_disclosure_present(
        self,
        generator: DescriptionGenerator,
        basic_input: DescriptionInput,
    ) -> None:
        """Amazon Associates required language must be present when Amazon links exist."""
        result = generator.generate_description(basic_input)
        assert "Amazon Associate" in result, "Amazon Associates disclosure missing"

    def test_no_ftc_when_no_affiliates(
        self,
        generator: DescriptionGenerator,
        sample_scenes: list[SceneBreakdown],
    ) -> None:
        """No FTC disclosure when there are no affiliate links."""
        input_data = DescriptionInput(
            video_id=uuid.uuid4(),
            title="Test",
            case_summary="A simple case summary for testing purposes.",
            scenes=sample_scenes,
            affiliate_config=AffiliateConfig(),  # no links
        )
        result = generator.generate_description(input_data)
        assert "FTC DISCLOSURE" not in result


class TestAIDisclosure:
    def test_ai_disclosure_present(
        self,
        generator: DescriptionGenerator,
        basic_input: DescriptionInput,
    ) -> None:
        """AI production disclosure must be included."""
        result = generator.generate_description(basic_input)
        assert "AI-assisted" in result or "AI" in result, "AI disclosure missing"

    def test_innocence_presumption_present(
        self,
        generator: DescriptionGenerator,
        basic_input: DescriptionInput,
    ) -> None:
        """Innocence presumption statement must be included."""
        result = generator.generate_description(basic_input)
        assert "presumed innocent" in result, "Innocence presumption missing"


class TestChapters:
    def test_chapters_start_at_zero(
        self,
        generator: DescriptionGenerator,
        sample_scenes: list[SceneBreakdown],
    ) -> None:
        """First chapter timestamp must be 0:00."""
        chapters = generator.generate_chapters(sample_scenes)
        assert chapters.startswith("0:00"), f"Chapters must start with 0:00, got: {chapters[:20]}"

    def test_chapters_minimum_three(
        self,
        generator: DescriptionGenerator,
        sample_scenes: list[SceneBreakdown],
    ) -> None:
        """YouTube requires at least 3 chapters for auto-detection."""
        chapters = generator.generate_chapters(sample_scenes)
        lines = [line for line in chapters.strip().split("\n") if line.strip()]
        assert len(lines) >= 3, f"Need at least 3 chapters, got {len(lines)}"

    def test_chapters_sorted_by_time(
        self,
        generator: DescriptionGenerator,
        sample_scenes: list[SceneBreakdown],
    ) -> None:
        """Chapter timestamps should be sorted chronologically."""
        chapters = generator.generate_chapters(sample_scenes)
        lines = [line for line in chapters.strip().split("\n") if line.strip()]

        times: list[float] = []
        for line in lines:
            ts = line.split(" ", 1)[0]
            parts = ts.split(":")
            if len(parts) == 2:
                seconds = int(parts[0]) * 60 + int(parts[1])
            else:
                seconds = int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])
            times.append(seconds)

        assert times == sorted(times), "Chapters should be in chronological order"

    def test_empty_scenes_returns_empty(
        self,
        generator: DescriptionGenerator,
    ) -> None:
        """No scenes should produce no chapters."""
        assert generator.generate_chapters([]) == ""


class TestSourceCitations:
    def test_source_icons_by_type(
        self,
        generator: DescriptionGenerator,
    ) -> None:
        """Each source type should get the correct icon prefix."""
        sources = [
            SourceCitation(title="Court Doc", source_type="court_document"),
            SourceCitation(title="News", source_type="news_article"),
            SourceCitation(title="Gov Report", source_type="government_report"),
        ]
        result = generator.generate_source_citations(sources)

        # Should contain type-appropriate icons
        assert "\U0001f4c4" in result  # 📄 court
        assert "\U0001f4f0" in result  # 📰 news
        assert "\U0001f3db" in result  # 🏛 government

    def test_timestamp_references_included(
        self,
        generator: DescriptionGenerator,
    ) -> None:
        """Sources with timestamp_reference should include it."""
        sources = [
            SourceCitation(
                title="Key Evidence",
                source_type="court_document",
                timestamp_reference="5:32",
            ),
        ]
        result = generator.generate_source_citations(sources)
        assert "5:32" in result


class TestHashtags:
    def test_hashtags_formatted(
        self,
        generator: DescriptionGenerator,
        basic_input: DescriptionInput,
    ) -> None:
        """Hashtags should be present and properly formatted with # prefix."""
        result = generator.generate_description(basic_input)
        assert "#TrueCrime" in result
        assert "#ColdCase" in result

    def test_max_five_hashtags(self) -> None:
        """At most 5 hashtags should appear."""
        result = DescriptionGenerator._generate_hashtags(["a", "b", "c", "d", "e", "f", "g"])
        assert result.count("#") == 5


class TestAffiliateBlock:
    def test_geniuslink_url_format(
        self,
        generator: DescriptionGenerator,
    ) -> None:
        """Amazon book link should use Geniuslink base when configured."""
        config = AffiliateConfig(
            geniuslink_base="https://geni.us/crimemill",
            amazon_tag="crimemill-20",
        )
        result = generator.generate_affiliate_block(
            config, book_title="Test Book", book_asin="B12345"
        )
        assert "geni.us/crimemill/dp/B12345" in result

    def test_fallback_amazon_url(
        self,
        generator: DescriptionGenerator,
    ) -> None:
        """Without Geniuslink, should use direct Amazon URL with tag."""
        config = AffiliateConfig(amazon_tag="crimemill-20")
        result = generator.generate_affiliate_block(
            config, book_title="Test Book", book_asin="B12345"
        )
        assert "amazon.com/dp/B12345?tag=crimemill-20" in result

    def test_empty_config_returns_empty(
        self,
        generator: DescriptionGenerator,
    ) -> None:
        """No affiliate links configured should return empty string."""
        result = generator.generate_affiliate_block(AffiliateConfig())
        assert result == ""
