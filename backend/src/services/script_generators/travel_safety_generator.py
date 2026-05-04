"""Travel-safety script generator.

Reformats a Rhyo intelligence report into a YouTube-ready script package
(title, 12-15 minute script, scene breakdown, image prompts, description,
destination tags) for the Street Level travel-safety channel. Does NOT
invent content — it restructures and re-voices the source report.

Multi-call pipeline (script -> scenes -> image prompts -> title ->
description) mirrors the crime ``ScriptGenerator`` for cost/observability
parity. The single public entry point is
``TravelSafetyScriptGenerator.run(report_path)``.
"""

from __future__ import annotations

import json
import re
from decimal import Decimal
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal, cast

import anthropic
import structlog
from pydantic import BaseModel, Field

from src.services.prompts import travel_prompts
from src.services.script_generator import MODEL_HAIKU, _calculate_cost
from src.services.script_generator import MODEL_SONNET as CRIME_MODEL_SONNET
from src.services.script_generator import (
    _strip_json_fences as _crime_strip_json_fences,
)

if TYPE_CHECKING:
    import httpx

    from src.config import Settings

logger = structlog.get_logger(__name__)


# (Legacy single-call TravelSafetyGenerator and its support models —
# TravelScene, TravelDestination, TravelScriptArtifacts, _strip_json_fences,
# _calculate_sonnet_cost, MODEL_SONNET — were removed. The multi-call
# TravelSafetyScriptGenerator below is the only generator in use.)


# ISO2 lookup for the country names that appear in Rhyo report headers.
# Conservative — covers the markets RHYO ships first. Unknown countries
# fall back to the first two upper-cased characters.
_COUNTRY_NAME_TO_ISO2: dict[str, str] = {
    "india": "IN",
    "mexico": "MX",
    "thailand": "TH",
    "indonesia": "ID",
    "vietnam": "VN",
    "philippines": "PH",
    "brazil": "BR",
    "colombia": "CO",
    "peru": "PE",
    "argentina": "AR",
    "chile": "CL",
    "south africa": "ZA",
    "kenya": "KE",
    "nigeria": "NG",
    "egypt": "EG",
    "morocco": "MA",
    "turkey": "TR",
    "pakistan": "PK",
    "bangladesh": "BD",
    "sri lanka": "LK",
    "malaysia": "MY",
    "japan": "JP",
    "south korea": "KR",
    "united states": "US",
    "usa": "US",
    "united kingdom": "GB",
    "uk": "GB",
    "france": "FR",
    "germany": "DE",
    "spain": "ES",
    "italy": "IT",
    "netherlands": "NL",
    "canada": "CA",
    "australia": "AU",
    "new zealand": "NZ",
    "russia": "RU",
    "ukraine": "UA",
}

_FORBIDDEN_VOICE_TOKENS: tuple[str, ...] = (
    "chilling",
    "shocking",
    "in a stunning turn of events",
    "authorities allege",
    "what you're about to see",
    "you won't believe",
)


class RhyoReport(BaseModel):
    """A parsed Rhyo Safety Intelligence Report — used as script input."""

    source_path: str
    location_name: str
    country_code: str = Field(min_length=2, max_length=2)
    region: str | None = None
    city: str | None = None
    coordinates: tuple[float, float] | None = None
    overall_day_score: float | None = None
    overall_night_score: float | None = None
    band: str | None = None
    confidence: float | None = None
    data_quality_warnings: list[str] = Field(default_factory=list)
    dominant_risks: list[str] = Field(default_factory=list)
    key_recommendations: list[str] = Field(default_factory=list)
    raw_markdown: str
    sections: dict[str, str] = Field(default_factory=dict)


class Scene(BaseModel):
    """One scene in the travel video — narration + visual + duration."""

    scene_id: int = Field(ge=1)
    narration: str
    duration_seconds: int = Field(ge=1)
    visual_description: str


class ImagePrompt(BaseModel):
    """One image generation prompt for a scene."""

    scene_id: int = Field(ge=1)
    prompt: str
    style: str  # "warm" | "moody"


class VideoDestination(BaseModel):
    """A destination tag, ready to insert into video_destinations."""

    country_code: str = Field(min_length=2, max_length=2)
    region_or_state: str | None = None
    city: str | None = None
    poi_name: str | None = None
    relevance: Literal["primary", "secondary", "mentioned"] = "primary"
    safepath_tags: list[str] = Field(default_factory=list)


class ScriptArtifacts(BaseModel):
    """Complete output of a TravelSafetyScriptGenerator.run() pass."""

    title: str
    script_text: str
    scenes: list[Scene]
    image_prompts: list[ImagePrompt]
    description: str
    destinations: list[VideoDestination]
    format: str
    source_report_path: str
    include_sponsor_credit: bool
    total_cost_usd: Decimal


# ---------------------------------------------------------------------------
# Parsing helpers (pure, side-effect free, importable for tests)
# ---------------------------------------------------------------------------

_LOCATION_LINE_RE = re.compile(r"^##\s+(.+?)\s*$", re.MULTILINE)
_COORDS_RE = re.compile(r"(\d+(?:\.\d+)?)°N,\s*(\d+(?:\.\d+)?)°E")
# Day score: matches "Overall Day Score | **65.1 / 100** | Guarded" and
# "| Day | 68.7 (Guarded — ..." and similar variations.
_DAY_SCORE_RE = re.compile(
    r"(?:Overall Day Score|^\|\s*Day)\s*\|\s*\*?\*?([\d.]+)(?:\s*/\s*100)?\*?\*?"
    r"(?:\s*\(?\s*\|?\s*([A-Z][a-z]+)\s*[\)\|—\-]?)?",
    re.MULTILINE,
)
_NIGHT_SCORE_RE = re.compile(
    r"(?:Overall Night Score|^\|\s*Night)\s*\|\s*\*?\*?([\d.]+)",
    re.MULTILINE,
)
# Confidence: matches "Confidence | 100%" and "Confidence | **1 / 100**"
_CONFIDENCE_RE = re.compile(
    r"Confidence\s*\|\s*\*?\*?([\d.]+)\s*(?:%|/\s*100)?",
    re.IGNORECASE,
)
_SECTION_HEADER_RE = re.compile(r"^##\s+(\d+)\.\s+(.+?)\s*$", re.MULTILINE)
_BOTTOM_LINE_RE = re.compile(r"^##\s+ONE-LINE BOTTOM LINE\s*$", re.MULTILINE)
_RISK_ROW_RE = re.compile(r"^\|\s*\*\*([a-z_]+)\*\*\s*\|\s*([\d.]+)\s*\|", re.MULTILINE)


def _tolerant_json_parse(text: str) -> dict[str, Any] | list[Any] | None:
    """Best-effort parse of an LLM JSON response.

    Tries, in order:
      1. Strip markdown fences and parse as-is.
      2. Slice from the first ``{`` / ``[`` to the matching closing brace
         (Haiku sometimes leaks a sentence of preamble or postamble).
      3. Fix unescaped double-quotes inside string values — the most common
         failure on Haiku scene_breakdown when a narration line contains
         a quoted phrase. We re-quote any ``"`` that is preceded by a word
         character and followed by a word character (i.e. clearly mid-word
         or mid-sentence, not a JSON delimiter).

    Returns the parsed object on success or ``None`` if every strategy
    failed. Callers decide whether to retry the LLM call.
    """
    candidate = _crime_strip_json_fences(text).strip()
    if not candidate:
        return None

    try:
        return cast("dict[str, Any] | list[Any]", json.loads(candidate))
    except json.JSONDecodeError:
        pass

    # Strategy 2: trim to outermost JSON container.
    starts = [i for i in (candidate.find("{"), candidate.find("[")) if i != -1]
    ends = [i for i in (candidate.rfind("}"), candidate.rfind("]")) if i != -1]
    if starts and ends:
        sliced = candidate[min(starts) : max(ends) + 1]
        try:
            return cast("dict[str, Any] | list[Any]", json.loads(sliced))
        except json.JSONDecodeError:
            candidate = sliced

    # Strategy 3: re-escape stray double quotes that are clearly inside a
    # narration string (word-character on both sides).
    repaired = re.sub(r'(?<=\w)"(?=\w)', r'\\"', candidate)
    try:
        return cast("dict[str, Any] | list[Any]", json.loads(repaired))
    except json.JSONDecodeError:
        return None


def _country_name_to_iso2(country_name: str) -> str:
    """Map a country name (lower or mixed case) to ISO 3166-1 alpha-2."""
    key = country_name.strip().lower()
    if key in _COUNTRY_NAME_TO_ISO2:
        return _COUNTRY_NAME_TO_ISO2[key]
    # Fallback: uppercase first 2 letters of the trimmed token. Not perfect
    # but deterministic and visible in logs.
    cleaned = re.sub(r"[^A-Za-z]", "", country_name)[:2].upper()
    return cleaned or "XX"


def _extract_sections(markdown: str) -> dict[str, str]:
    """Return a dict mapping `N. SECTION NAME` -> body text up to next ##."""
    out: dict[str, str] = {}
    headers = list(_SECTION_HEADER_RE.finditer(markdown))
    bottom_line = _BOTTOM_LINE_RE.search(markdown)
    boundaries: list[tuple[str, int, int]] = []
    for i, h in enumerate(headers):
        name = f"{h.group(1)}. {h.group(2).strip()}"
        start = h.end()
        end = (
            headers[i + 1].start()
            if i + 1 < len(headers)
            else (bottom_line.start() if bottom_line else len(markdown))
        )
        boundaries.append((name, start, end))
    for name, start, end in boundaries:
        out[name] = markdown[start:end].strip()
    if bottom_line:
        # Bottom line body runs from after the header to EOF
        body_start = bottom_line.end()
        out["ONE-LINE BOTTOM LINE"] = markdown[body_start:].strip()
    return out


def _extract_dominant_risks(markdown: str) -> list[str]:
    """Pull the top 3 risk_column rows from §2 by descending value."""
    rows = _RISK_ROW_RE.findall(markdown)
    if not rows:
        return []
    typed: list[tuple[str, float]] = []
    for name, value in rows:
        try:
            typed.append((name, float(value)))
        except ValueError:
            continue
    typed.sort(key=lambda r: r[1], reverse=True)
    return [name for name, _ in typed[:3]]


def _extract_data_quality_warnings(markdown: str) -> list[str]:
    """Scan §10 (and the doc head) for confidence / fallback / OOM / stale flags."""
    warnings: list[str] = []
    section_match = re.search(
        r"##\s+10\.\s+RHYO DATA QUALITY DISCLOSURES(.+?)(?=^##\s|\Z)",
        markdown,
        re.MULTILINE | re.DOTALL,
    )
    section = section_match.group(1) if section_match else ""
    flag_re = re.compile(
        r"(data quality|fallback|lighting artifact|OOM|stale|confidence[- ]?\d+|"
        r"low confidence|degraded|null|not yet computed|preserved for transparency)",
        re.IGNORECASE,
    )
    for line in section.splitlines():
        line = line.strip().lstrip("-*").strip()
        if not line:
            continue
        if flag_re.search(line):
            warnings.append(line[:240])
    # Also catch top-of-doc warnings (some reports put them above §1)
    head = markdown.split("## 1.", 1)[0]
    for line in head.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if flag_re.search(line):
            warnings.append(line[:240])
    return warnings


def _extract_recommendations(sections: dict[str, str]) -> list[str]:
    """Pull bullet lines from §9 + the bottom line as candidate recommendations."""
    recs: list[str] = []
    for name, body in sections.items():
        if name.startswith("9.") or name == "ONE-LINE BOTTOM LINE":
            for line in body.splitlines():
                stripped = line.strip()
                if not stripped:
                    continue
                if (
                    stripped.startswith(("- ", "* ", "1.", "2.", "3.", "4.", "5."))
                    or name == "ONE-LINE BOTTOM LINE"
                ):
                    recs.append(stripped.lstrip("-*0123456789. ").strip()[:280])
    return [r for r in recs if r]


def _parse_location_header(markdown: str) -> tuple[str, str | None, str | None, str]:
    """Return (location_name, region, city, country_code) from the H1+H2 lines."""
    # Find the H2 immediately after the H1
    h1_match = re.search(r"^#\s+RHYO Safety Intelligence Report\s*$", markdown, re.MULTILINE)
    location_name = ""
    if h1_match:
        rest = markdown[h1_match.end() :]
        h2_match = re.search(r"^##\s+(.+?)\s*$", rest, re.MULTILINE)
        if h2_match:
            location_name = h2_match.group(1).strip()
    if not location_name:
        # fallback to first H2 in the doc
        h2 = _LOCATION_LINE_RE.search(markdown)
        location_name = h2.group(1).strip() if h2 else "Unknown Location"

    parts = [p.strip() for p in location_name.split(",") if p.strip()]
    country = parts[-1] if parts else "Unknown"
    city = parts[-3] if len(parts) >= 3 else (parts[-2] if len(parts) >= 2 else None)
    region = parts[-2] if len(parts) >= 4 else (parts[-2] if len(parts) >= 3 else None)
    # Refine region: when the trailing tokens are city, region, country, region == parts[-2]
    if len(parts) >= 3:
        region = parts[-2]
        city = parts[-3]
    elif len(parts) == 2:
        region = None
        city = parts[0]
    country_code = _country_name_to_iso2(country)
    return location_name, region, city, country_code


def _country_code_from_markdown_body(markdown: str, fallback: str) -> str:
    """If the header didn't yield a clean ISO2, scan the body for a known
    country name. Used when the H2 omits the country (e.g. 'Old City
    Hyderabad' rather than '..., Hyderabad, Telangana, India').
    """
    if fallback in {
        "IN",
        "MX",
        "TH",
        "ID",
        "VN",
        "PH",
        "BR",
        "CO",
        "PE",
        "AR",
        "CL",
        "ZA",
        "KE",
        "NG",
        "EG",
        "MA",
        "TR",
        "PK",
        "BD",
        "LK",
        "MY",
        "JP",
        "KR",
        "US",
        "GB",
        "FR",
        "DE",
        "ES",
        "IT",
        "NL",
        "CA",
        "AU",
        "NZ",
        "RU",
        "UA",
    }:
        return fallback
    md_lower = markdown.lower()
    for name, iso in _COUNTRY_NAME_TO_ISO2.items():
        # Word-boundary match to avoid 'india' inside 'indiana'
        if re.search(rf"\b{re.escape(name)}\b", md_lower):
            return iso
    return fallback


def _safe_float(s: str) -> float | None:
    try:
        return float(s)
    except (TypeError, ValueError):
        return None


def parse_rhyo_report(filepath: str | Path) -> RhyoReport:
    """Parse a Rhyo intelligence report markdown file into a RhyoReport.

    Tolerant: missing fields become None / empty lists rather than raising.
    """
    path = Path(filepath)
    markdown = path.read_text(encoding="utf-8")

    location_name, region, city, country_code = _parse_location_header(markdown)
    country_code = _country_code_from_markdown_body(markdown, country_code)

    coords: tuple[float, float] | None = None
    cm = _COORDS_RE.search(markdown)
    if cm:
        lat = _safe_float(cm.group(1))
        lon = _safe_float(cm.group(2))
        if lat is not None and lon is not None:
            coords = (lat, lon)

    day_score: float | None = None
    band: str | None = None
    dm = _DAY_SCORE_RE.search(markdown)
    if dm:
        day_score = _safe_float(dm.group(1))
        band = dm.group(2).strip()

    night_score: float | None = None
    nm = _NIGHT_SCORE_RE.search(markdown)
    if nm:
        night_score = _safe_float(nm.group(1))

    confidence: float | None = None
    cnf = _CONFIDENCE_RE.search(markdown)
    if cnf:
        confidence = _safe_float(cnf.group(1))

    sections = _extract_sections(markdown)
    dominant_risks = _extract_dominant_risks(markdown)
    warnings = _extract_data_quality_warnings(markdown)
    recommendations = _extract_recommendations(sections)

    # Best-effort POI extraction from location_name first segment
    return RhyoReport(
        source_path=str(path),
        location_name=location_name,
        country_code=country_code,
        region=region,
        city=city,
        coordinates=coords,
        overall_day_score=day_score,
        overall_night_score=night_score,
        band=band,
        confidence=confidence,
        data_quality_warnings=warnings,
        dominant_risks=dominant_risks,
        key_recommendations=recommendations,
        raw_markdown=markdown,
        sections=sections,
    )


# ---------------------------------------------------------------------------
# TravelSafetyScriptGenerator — multi-call pipeline
# ---------------------------------------------------------------------------

# Use the same model IDs as the crime ScriptGenerator. This keeps cost
# accounting and rate-limit logic consistent across niches.
_TS_MODEL_SONNET = CRIME_MODEL_SONNET
_TS_MODEL_HAIKU = MODEL_HAIKU


class TravelSafetyScriptGenerator:
    """Multi-call travel-safety script generator.

    Orchestrates: load report -> select format -> 5 Claude calls
    (script / scenes / image prompts / title / description) -> destination
    extraction -> assembled ScriptArtifacts.

    Constructor signature mirrors ``ScriptGenerator`` for interface
    consistency. Pass ``client=`` to inject a mock Anthropic client in tests.
    """

    def __init__(
        self,
        settings: Settings,
        http_client: httpx.AsyncClient,
        *,
        client: anthropic.AsyncAnthropic | None = None,
    ) -> None:
        self._settings = settings
        self._http = http_client
        self._client = client or anthropic.AsyncAnthropic(api_key=settings.anthropic.api_key)

    # ------------------------------------------------------------------ loaders

    @staticmethod
    def load_rhyo_report(filepath: str | Path) -> RhyoReport:
        """Parse a Rhyo intelligence report from disk into a RhyoReport."""
        return parse_rhyo_report(filepath)

    # ------------------------------------------------------------------ format

    @staticmethod
    def select_video_format(report: RhyoReport) -> str:
        """Pick one of the five video formats based on report content.

        Crisis trigger uses the report's structural flags ("Conflict zone:
        true", "Informal settlement: true") and severely degraded
        confidence — NOT free-text OOM/maintenance mentions, which are
        infrastructure notes rather than safety signals.
        """
        md_lower = report.raw_markdown.lower()
        has_structural_crisis = (
            "conflict zone | true" in md_lower
            or "conflict zone: true" in md_lower
            or "informal settlement | true" in md_lower
            or "informal settlement: true" in md_lower
        )
        if (report.confidence is not None and report.confidence < 30) or has_structural_crisis:
            return "crisis_response"

        # "Guarded or worse" per the prompt narrative — Guarded includes
        # locations like Banjara Hills where road / air / disease hazards
        # dominate even though score is mid-band.
        if (report.overall_day_score is not None and report.overall_day_score < 60) or (
            report.band in ("Guarded", "Elevated", "Critical")
        ):
            return "safety_briefing"

        scam_terms = ("scam", "drink-spiking", "honey-trap", "skimming")
        scam_hits = sum(
            len(re.findall(rf"\b{re.escape(t)}\b", report.raw_markdown, re.IGNORECASE))
            for t in scam_terms
        )
        if scam_hits >= 3:
            return "scam_anatomy"

        if report.overall_day_score is not None and report.overall_day_score >= 75:
            return "things_to_do"

        return "destination_guide"

    # ------------------------------------------------------------------ helpers

    async def _call(
        self,
        *,
        model: str,
        system_prompt: str,
        user_message: str,
        max_tokens: int,
        temperature: float,
    ) -> tuple[str, Decimal]:
        """One Claude call with cost calculation. Mirrors crime _call_claude."""
        response = await self._client.messages.create(
            model=model,
            max_tokens=max_tokens,
            temperature=temperature,
            system=[
                {
                    "type": "text",
                    "text": system_prompt,
                    "cache_control": {"type": "ephemeral"},
                }
            ],
            messages=[{"role": "user", "content": user_message}],
        )
        text = response.content[0].text  # type: ignore[union-attr]
        usage = response.usage
        cached = getattr(usage, "cache_creation_input_tokens", 0) + getattr(
            usage, "cache_read_input_tokens", 0
        )
        cost = _calculate_cost(model, usage.input_tokens, usage.output_tokens, cached)
        return text, cost

    # ------------------------------------------------------------------ stages

    async def generate_script(self, report: RhyoReport, format: str) -> tuple[str, Decimal]:
        """Sonnet call: produce the 12-15 minute script."""
        user_message = f"FORMAT: {format}\n\n{report.raw_markdown}"
        text, cost = await self._call(
            model=_TS_MODEL_SONNET,
            system_prompt=travel_prompts.SCRIPT_SYSTEM_PROMPT,
            user_message=user_message,
            max_tokens=8000,
            temperature=1.0,
        )
        return text.strip(), cost

    async def generate_scene_breakdown(self, script: str) -> tuple[list[Scene], Decimal]:
        """Haiku call: turn the script into 20-30 scenes.

        Haiku occasionally emits unescaped quotes inside narration strings
        or wraps the JSON in markdown fences. Use the tolerant parser and
        retry once with a stricter reminder if the first parse fails.
        """
        text, cost = await self._call(
            model=_TS_MODEL_HAIKU,
            system_prompt=travel_prompts.SCENE_BREAKDOWN_SYSTEM_PROMPT,
            user_message=script,
            max_tokens=4096,
            temperature=0.7,
        )
        data = _tolerant_json_parse(text)
        if data is None:
            retry_msg = (
                f"{script}\n\n"
                "REMINDER: Return ONLY a strict JSON object — no markdown "
                "fences, no commentary. Escape every double-quote inside "
                "narration strings as \\\"."
            )
            retry_text, retry_cost = await self._call(
                model=_TS_MODEL_HAIKU,
                system_prompt=travel_prompts.SCENE_BREAKDOWN_SYSTEM_PROMPT,
                user_message=retry_msg,
                max_tokens=4096,
                temperature=0.3,
            )
            cost = (cost + retry_cost).quantize(Decimal("0.000001"))
            data = _tolerant_json_parse(retry_text)
            if data is None:
                raise ValueError(
                    "Haiku scene_breakdown returned malformed JSON twice; "
                    f"last response head: {retry_text[:300]!r}"
                )
        scenes_raw = data.get("scenes", []) if isinstance(data, dict) else data
        scenes = [Scene.model_validate(s) for s in scenes_raw]
        return scenes, cost

    async def generate_image_prompts(
        self, scenes: list[Scene]
    ) -> tuple[list[ImagePrompt], Decimal]:
        """Haiku call: one image prompt per scene."""
        payload = json.dumps(
            [{"scene_id": s.scene_id, "visual_description": s.visual_description} for s in scenes]
        )
        # 30 scenes x ~120 tokens each (prompt + style + scene_id wrapping)
        # plus JSON overhead — give 6k tokens to avoid truncation mid-array.
        text, cost = await self._call(
            model=_TS_MODEL_HAIKU,
            system_prompt=travel_prompts.IMAGE_PROMPT_SYSTEM_PROMPT,
            user_message=payload,
            max_tokens=6000,
            temperature=0.7,
        )
        data = json.loads(_crime_strip_json_fences(text))
        prompts_raw = data.get("prompts", []) if isinstance(data, dict) else data
        prompts = [ImagePrompt.model_validate(p) for p in prompts_raw]
        return prompts, cost

    async def generate_title(self, report: RhyoReport, script: str) -> tuple[str, Decimal]:
        """Sonnet call: 6 candidate titles, return the first."""
        user_message = (
            f"LOCATION: {report.location_name}\n"
            f"COUNTRY: {report.country_code}\n\n"
            f"SCRIPT:\n{script[:6000]}"
        )
        text, cost = await self._call(
            model=_TS_MODEL_SONNET,
            system_prompt=travel_prompts.TITLE_SYSTEM_PROMPT,
            user_message=user_message,
            max_tokens=600,
            temperature=0.9,
        )
        data = json.loads(_crime_strip_json_fences(text))
        titles = data.get("titles", []) if isinstance(data, dict) else []
        if not titles:
            return report.location_name, cost
        return str(titles[0]), cost

    async def generate_description(
        self, report: RhyoReport, script: str
    ) -> tuple[str, bool, Decimal]:
        """Haiku call: YouTube description + sponsor credit flag."""
        user_message = (
            f"LOCATION: {report.location_name}\n"
            f"COUNTRY: {report.country_code}\n\n"
            f"SCRIPT EXCERPT:\n{script[:5000]}"
        )
        text, cost = await self._call(
            model=_TS_MODEL_HAIKU,
            system_prompt=travel_prompts.DESCRIPTION_SYSTEM_PROMPT,
            user_message=user_message,
            max_tokens=1500,
            temperature=0.7,
        )
        data = json.loads(_crime_strip_json_fences(text))
        description = str(data.get("description", "")) if isinstance(data, dict) else ""
        include = bool(data.get("include_sponsor_credit", False)) if isinstance(data, dict) else False
        return description, include, cost

    # ------------------------------------------------------------------ destinations

    @staticmethod
    def extract_destinations(
        report: RhyoReport, script: str, format: str
    ) -> list[VideoDestination]:
        """Build VideoDestination rows from the parsed report.

        Pure logic: produces at least one primary destination from the
        report's location header. POI is the first comma-separated segment
        of the location name when more than just city / region / country
        are present (e.g. "Road No. 14, Banjara Hills, Hyderabad, ...").
        """
        parts = [p.strip() for p in report.location_name.split(",") if p.strip()]
        poi: str | None = None
        if len(parts) >= 4:
            # First two tokens are typically street + neighborhood — use
            # the neighborhood as the POI label
            poi = parts[1] if len(parts[1]) <= 80 else parts[0]
        elif len(parts) >= 1:
            poi = parts[0] if parts[0] != (report.city or "") else None

        primary = VideoDestination(
            country_code=report.country_code,
            region_or_state=report.region,
            city=report.city,
            poi_name=poi,
            relevance="primary",
            safepath_tags=[format],
        )
        return [primary]

    # ------------------------------------------------------------------ orchestration

    async def run(self, report_path: str | Path) -> ScriptArtifacts:
        """End-to-end pipeline: load -> 5 Claude calls -> assemble."""
        report = self.load_rhyo_report(report_path)
        format = self.select_video_format(report)

        script_text, c1 = await self.generate_script(report, format)
        scenes, c2 = await self.generate_scene_breakdown(script_text)
        image_prompts, c3 = await self.generate_image_prompts(scenes)
        title, c4 = await self.generate_title(report, script_text)
        description, include_sponsor, c5 = await self.generate_description(report, script_text)
        destinations = self.extract_destinations(report, script_text, format)

        total_cost = (c1 + c2 + c3 + c4 + c5).quantize(Decimal("0.000001"))

        return ScriptArtifacts(
            title=title,
            script_text=script_text,
            scenes=scenes,
            image_prompts=image_prompts,
            description=description,
            destinations=destinations,
            format=format,
            source_report_path=str(report_path),
            include_sponsor_credit=include_sponsor,
            total_cost_usd=total_cost,
        )

    # ------------------------------------------------------------------ dry-run

    def build_assembled_prompts(self, report_path: str | Path) -> dict[str, str]:
        """Build the prompts that would be sent — no API calls.

        Useful for ``--print-only`` CLI inspection and offline auditing.
        Returns ``{stage_name: full_prompt}`` where ``full_prompt`` is the
        system prompt + a separator + the user message that would be sent
        to Claude for that stage.
        """
        report = self.load_rhyo_report(report_path)
        format = self.select_video_format(report)

        sep = "\n\n--- USER ---\n\n"
        script_user = f"FORMAT: {format}\n\n{report.raw_markdown}"
        # Scene / image / title / description stages depend on the script
        # output, which we don't have without making a call. Emit
        # placeholders that show the system prompt and the deterministic
        # parts of the user message.
        title_user = (
            f"LOCATION: {report.location_name}\n"
            f"COUNTRY: {report.country_code}\n\n"
            f"SCRIPT:\n<SCRIPT_TEXT_PLACEHOLDER>"
        )
        description_user = (
            f"LOCATION: {report.location_name}\n"
            f"COUNTRY: {report.country_code}\n\n"
            f"SCRIPT EXCERPT:\n<SCRIPT_TEXT_PLACEHOLDER>"
        )
        return {
            "format": format,
            "script": travel_prompts.SCRIPT_SYSTEM_PROMPT + sep + script_user,
            "scene_breakdown": (
                travel_prompts.SCENE_BREAKDOWN_SYSTEM_PROMPT + sep + "<SCRIPT_TEXT_PLACEHOLDER>"
            ),
            "image_prompts": (
                travel_prompts.IMAGE_PROMPT_SYSTEM_PROMPT + sep + "<SCENE_LIST_JSON_PLACEHOLDER>"
            ),
            "title": travel_prompts.TITLE_SYSTEM_PROMPT + sep + title_user,
            "description": (travel_prompts.DESCRIPTION_SYSTEM_PROMPT + sep + description_user),
        }


__all__ = [
    "ImagePrompt",
    "RhyoReport",
    "Scene",
    "ScriptArtifacts",
    "TravelSafetyScriptGenerator",
    "VideoDestination",
    "parse_rhyo_report",
]
