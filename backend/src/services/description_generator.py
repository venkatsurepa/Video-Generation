"""YouTube description generator — SEO-optimized descriptions with legal compliance.

Produces complete video descriptions that respect YouTube's 5,000-byte limit
and include properly formatted chapters, source citations, affiliate links
with FTC/Amazon disclosures, channel links, and legal disclaimers.

Structure is optimised for search: the first 2-3 lines are visible in search
results and above "Show more," so the hook line and source teaser go first.
"""

from __future__ import annotations

import math
from pathlib import Path
from typing import TYPE_CHECKING

import structlog

if TYPE_CHECKING:
    from src.config import Settings
    from src.models.description import (
        AffiliateConfig,
        ChannelLinks,
        DescriptionInput,
        SourceCitation,
    )
    from src.models.script import SceneBreakdown

logger = structlog.get_logger()

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

YOUTUBE_MAX_BYTES: int = 5_000
# Leave 100 bytes of headroom so we never clip on a multi-byte char boundary
SAFE_MAX_BYTES: int = 4_900

_SOURCE_ICONS: dict[str, str] = {
    "court_document": "\U0001f4c4",  # 📄
    "news_article": "\U0001f4f0",  # 📰
    "government_report": "\U0001f3db",  # 🏛
    "academic": "\U0001f393",  # 🎓
    "other": "\U0001f517",  # 🔗
}

_TEMPLATE_PATH = (
    Path(__file__).resolve().parents[2] / "assets" / "templates" / "description_template.txt"
)


# ---------------------------------------------------------------------------
# DescriptionGenerator
# ---------------------------------------------------------------------------


class DescriptionGenerator:
    """Generates complete, SEO-optimized YouTube descriptions.

    The output follows a strict section order designed to maximise both
    search ranking and viewer trust:

    1. Hook line (visible in search results)
    2. Source teaser
    3. Keyword-rich case summary
    4. Chapter timestamps
    5. Source citations
    6. Affiliate links (FTC disclosure first)
    7. Channel links
    8. Legal disclaimer (innocence + AI disclosure)
    9. Hashtags (first 3 appear above the title)

    All text is kept under YouTube's 5,000-byte limit.

    Parameters
    ----------
    settings:
        Application settings.  Currently unused but accepted for interface
        consistency with other pipeline services.
    """

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._template = self._load_template()

    # ==================================================================
    # Public API
    # ==================================================================

    def generate_description(self, input: DescriptionInput) -> str:
        """Generate a complete YouTube video description.

        Parameters
        ----------
        input:
            All metadata needed: title, summary, scenes (for chapters),
            sources, affiliate config, channel links, and hashtags.

        Returns
        -------
        str
            A ready-to-paste YouTube description, guaranteed under 5,000
            bytes UTF-8.
        """
        hook_line = self._generate_hook_line(input.title, input.case_summary)
        sources_teaser = "\U0001f50e Sources & case documents linked below"
        case_summary = input.case_summary.strip()
        chapters = self.generate_chapters(input.scenes)
        sources = self.generate_source_citations(input.sources)
        affiliate_block = self.generate_affiliate_block(
            input.affiliate_config,
            input.related_book_title,
            input.related_book_asin,
        )
        channel_links = self._generate_channel_links(input.channel_links)
        legal_disclaimer = self._generate_legal_disclaimer()
        hashtags = self._generate_hashtags(input.hashtags)

        # Assemble using the template slot order
        sections: dict[str, str] = {
            "hook_line": hook_line,
            "sources_teaser": sources_teaser,
            "case_summary": case_summary,
            "chapters": chapters,
            "sources": sources,
            "affiliate_block": affiliate_block,
            "channel_links": channel_links,
            "legal_disclaimer": legal_disclaimer,
            "hashtags": hashtags,
        }

        description = self._template
        for key, value in sections.items():
            description = description.replace(f"{{{key}}}", value)

        # Collapse triple+ blank lines into double
        while "\n\n\n" in description:
            description = description.replace("\n\n\n", "\n\n")

        description = description.strip()

        # Enforce byte limit
        if self._count_bytes(description) > SAFE_MAX_BYTES:
            description = self._truncate_to_limit(description, SAFE_MAX_BYTES)

        return description

    # ------------------------------------------------------------------

    def generate_chapters(self, scenes: list[SceneBreakdown]) -> str:
        """Generate YouTube chapter timestamps from the scene breakdown.

        Rules:
        - Must start with ``0:00``.
        - Each chapter title is under 50 characters.
        - Chapters align with ad-break positions where possible.
        - Minimum 3 chapters, aiming for one every 2-4 minutes.

        Parameters
        ----------
        scenes:
            Ordered scene breakdowns with timing and ad-break flags.

        Returns
        -------
        str
            Formatted chapter block ready for embedding in the description.
        """
        if not scenes:
            return ""

        lines: list[str] = []

        # Always start with 0:00
        first_title = self._chapter_title(scenes[0], fallback="Introduction")
        lines.append(f"0:00 {first_title}")

        # Build chapter points from scene boundaries
        seen_times: set[str] = {"0:00"}

        for scene in scenes[1:]:
            ts = _format_timestamp(scene.start_time_seconds)
            if ts in seen_times:
                continue

            # Prefer ad-break or pattern-interrupt scenes as chapter starts
            # but include any scene that starts a meaningfully new section
            title = self._chapter_title(scene)
            if not title:
                continue

            lines.append(f"{ts} {title}")
            seen_times.add(ts)

        # YouTube requires at least 3 chapters for auto-generation
        if len(lines) < 3 and len(scenes) >= 3:
            # Fill with evenly spaced scenes
            total_duration = scenes[-1].end_time_seconds
            interval = total_duration / 4
            for i in range(1, 4):
                t = interval * i
                ts = _format_timestamp(t)
                if ts not in seen_times:
                    # Find nearest scene
                    nearest = min(scenes, key=lambda s: abs(s.start_time_seconds - t))
                    title = self._chapter_title(nearest, fallback=f"Part {i + 1}")
                    lines.append(f"{ts} {title}")
                    seen_times.add(ts)

        # Sort by timestamp
        lines.sort(key=lambda line: _parse_timestamp(line.split(" ", 1)[0]))

        return "\n".join(lines)

    # ------------------------------------------------------------------

    def generate_affiliate_block(
        self,
        config: AffiliateConfig,
        book_title: str | None = None,
        book_asin: str | None = None,
    ) -> str:
        """Build the affiliate links section with required FTC disclosures.

        FTC disclosure appears **before** any affiliate links (legally
        required).  The Amazon Associates disclosure uses the exact language
        required by the programme terms.

        Geniuslink URLs auto-localise Amazon links across 19+ storefronts.

        Parameters
        ----------
        config:
            Per-channel affiliate configuration.
        book_title:
            Optional related book title for Amazon link.
        book_asin:
            Optional Amazon ASIN for the related book.

        Returns
        -------
        str
            Formatted affiliate block, or empty string if no links configured.
        """
        links: list[str] = []

        if config.vpn_link:
            links.append(
                f"\U0001f512 Protect your identity with {config.vpn_name} \u2014 {config.vpn_link}"
            )

        if config.audible_link:
            links.append(
                f"\U0001f4da Get this story on Audible (free trial) \u2014 {config.audible_link}"
            )

        if config.security_link:
            links.append(
                f"\U0001f3e0 {config.security_name} home security \u2014 {config.security_link}"
            )

        # Amazon book link
        has_amazon = False
        if book_title and book_asin:
            if config.geniuslink_base:
                book_url = f"{config.geniuslink_base}/dp/{book_asin}"
            elif config.amazon_tag:
                book_url = f"https://www.amazon.com/dp/{book_asin}?tag={config.amazon_tag}"
            else:
                book_url = f"https://www.amazon.com/dp/{book_asin}"
            links.append(f'\U0001f4d6 "{book_title}" \u2014 {book_url}')
            has_amazon = True

        if not links:
            return ""

        # FTC disclosure MUST come before the links
        ftc = (
            "\u26a1 FTC DISCLOSURE: This description contains affiliate links. "
            "I earn a commission on purchases at no extra cost to you."
        )

        parts = [ftc, ""]
        parts.extend(links)

        # Amazon Associates required language
        if has_amazon or config.amazon_tag:
            parts.append("\U0001f4d6 As an Amazon Associate I earn from qualifying purchases.")

        return "\n".join(parts)

    # ------------------------------------------------------------------

    def generate_source_citations(
        self,
        sources: list[SourceCitation],
    ) -> str:
        """Format source citations for the description.

        Each source is prefixed with a type-appropriate icon and optionally
        includes a timestamp reference showing where in the video the source
        is cited.

        Parameters
        ----------
        sources:
            Ordered list of source citations.

        Returns
        -------
        str
            Formatted source block, or empty string if no sources provided.
        """
        if not sources:
            return ""

        lines: list[str] = []
        for src in sources:
            icon = _SOURCE_ICONS.get(src.source_type, "\U0001f517")

            parts: list[str] = [icon, src.title]

            if src.publication_date:
                parts.append(f"({src.publication_date.isoformat()})")

            if src.url:
                parts.append(f"\u2014 {src.url}")

            line = " ".join(parts)

            if src.timestamp_reference:
                line = f"{src.timestamp_reference} \u2014 {line}"

            lines.append(line)

        return "\n".join(lines)

    # ==================================================================
    # Byte counting & truncation
    # ==================================================================

    def _count_bytes(self, text: str) -> int:
        """Return the UTF-8 byte length.  YouTube enforces bytes, not chars."""
        return len(text.encode("utf-8"))

    def _truncate_to_limit(
        self,
        text: str,
        max_bytes: int = SAFE_MAX_BYTES,
    ) -> str:
        """Safely truncate text to a UTF-8 byte limit.

        Trims from the end, section by section, preserving the most
        important top-of-description content.  Falls back to a hard byte
        slice that avoids splitting multi-byte characters.
        """
        if self._count_bytes(text) <= max_bytes:
            return text

        # Strategy: remove sections from the bottom until we fit.
        # The section order in the template is most-important-first,
        # so we trim the least important (hashtags, channel links, etc.)
        # by chopping lines from the end.
        lines = text.split("\n")
        while lines and self._count_bytes("\n".join(lines)) > max_bytes:
            lines.pop()

        result = "\n".join(lines).rstrip()

        # Final safety net: hard byte truncation
        if self._count_bytes(result) > max_bytes:
            encoded = result.encode("utf-8")[:max_bytes]
            result = encoded.decode("utf-8", errors="ignore").rstrip()

        return result

    # ==================================================================
    # Internal helpers
    # ==================================================================

    @staticmethod
    def _load_template() -> str:
        """Load the description template from the assets directory."""
        if _TEMPLATE_PATH.exists():
            return _TEMPLATE_PATH.read_text(encoding="utf-8")

        # Inline fallback if the file is missing
        return (
            "{hook_line}\n\n"
            "{sources_teaser}\n\n"
            "{case_summary}\n\n"
            "{chapters}\n\n"
            "{sources}\n\n"
            "{affiliate_block}\n\n"
            "{channel_links}\n\n"
            "{legal_disclaimer}\n\n"
            "{hashtags}\n"
        )

    @staticmethod
    def _generate_hook_line(title: str, summary: str) -> str:
        """Create a one-sentence hook visible in search results.

        Takes the first sentence of the summary (or truncates to ~150
        chars) because this is the most important line — it appears in
        YouTube search results and suggested-video cards.
        """
        # Use the first sentence of the summary as the hook
        first_sentence = summary.split(". ")[0].strip()
        if not first_sentence.endswith("."):
            first_sentence += "."

        # YouTube search previews show roughly 100-150 chars
        if len(first_sentence) > 150:
            first_sentence = first_sentence[:147].rstrip() + "..."

        return first_sentence

    @staticmethod
    def _chapter_title(
        scene: SceneBreakdown,
        fallback: str | None = None,
    ) -> str:
        """Extract a clean chapter title from a scene description.

        Strips it to under 50 chars for YouTube chapter display.
        """
        # Use the scene description as the chapter title, trimmed
        raw = scene.scene_description.strip()
        if not raw and fallback:
            return fallback
        if not raw:
            return ""

        # Take the first clause/sentence
        for sep in (". ", " - ", " — ", "; ", ", "):
            if sep in raw:
                raw = raw.split(sep)[0]
                break

        # Sentence-case and trim
        title = raw.strip().rstrip(".")
        if len(title) > 47:
            title = title[:44].rstrip() + "..."

        return title

    @staticmethod
    def _generate_channel_links(links: ChannelLinks) -> str:
        """Build the channel links section."""
        parts: list[str] = []

        if links.subscribe_url:
            parts.append(f"\U0001f514 Subscribe: {links.subscribe_url}")
        if links.podcast_url:
            parts.append(f"\U0001f3a7 Podcast: {links.podcast_url}")
        if links.discord_invite:
            parts.append(f"\U0001f4ac Discord: {links.discord_invite}")
        if links.ko_fi_url:
            parts.append(f"\u2615 Support on Ko-fi: {links.ko_fi_url}")
        if links.twitter_url:
            parts.append(f"\U0001f426 Twitter/X: {links.twitter_url}")
        if links.instagram_url:
            parts.append(f"\U0001f4f7 Instagram: {links.instagram_url}")

        return "\n".join(parts)

    @staticmethod
    def _generate_legal_disclaimer() -> str:
        """Build the dual legal disclaimer (innocence + AI disclosure).

        Both disclosures are legally required:
        - Innocence presumption for any unresolved cases.
        - AI production disclosure per platform policies and Apple Podcasts
          metadata requirements.
        """
        return (
            "\u2696\ufe0f All individuals not convicted are presumed innocent. "
            "This video is for educational and documentary purposes. Content "
            "based on publicly available court records, news reports, and "
            "official filings.\n"
            "\n"
            "This video uses AI-assisted production tools for narration, "
            "imagery, and research. All scripts are human-edited and "
            "fact-checked."
        )

    @staticmethod
    def _generate_hashtags(tags: list[str]) -> str:
        """Format hashtags.  First 3 appear above the video title."""
        if not tags:
            return ""

        formatted = []
        for tag in tags[:5]:
            t = tag.strip().lstrip("#")
            if t:
                formatted.append(f"#{t}")

        return " ".join(formatted)


# ---------------------------------------------------------------------------
# Module-level helpers
# ---------------------------------------------------------------------------


def _format_timestamp(seconds: float) -> str:
    """Convert seconds to ``M:SS`` or ``H:MM:SS`` timestamp."""
    total = int(math.floor(seconds))
    h, remainder = divmod(total, 3600)
    m, s = divmod(remainder, 60)
    if h > 0:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m}:{s:02d}"


def _parse_timestamp(ts: str) -> float:
    """Parse a ``M:SS`` or ``H:MM:SS`` string back to seconds."""
    parts = ts.split(":")
    if len(parts) == 3:
        return int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])
    if len(parts) == 2:
        return int(parts[0]) * 60 + int(parts[1])
    return 0.0
