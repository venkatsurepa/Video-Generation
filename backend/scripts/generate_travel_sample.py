"""Generate a sample travel-safety script from a Hyderabad fixture.

Run from backend/: python scripts/generate_travel_sample.py

Uses the multi-call TravelSafetyScriptGenerator (5 separate Claude calls —
script / scenes / image prompts / title / description) to avoid the 8192
output-token cap that truncates the single-call TravelSafetyGenerator on
12-15 minute scripts.

Prints title, first 500 chars of script, scene count, image prompt count,
description, destinations, and total cost. Requires a working
ANTHROPIC_API_KEY in .env.
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import httpx  # noqa: E402

from src.config import get_settings  # noqa: E402
from src.services.script_generators.travel_safety_generator import (  # noqa: E402
    TravelSafetyScriptGenerator,
)

REPORT_PATH = Path(__file__).resolve().parent.parent / "fixtures" / "rhyo_reports" / "hyderabad_banjara_hills.md"


async def main() -> int:
    settings = get_settings()
    if not settings.anthropic.api_key or settings.anthropic.api_key == "REPLACE_ME":
        print("ANTHROPIC_API_KEY missing or still REPLACE_ME — cannot run live sample.")
        return 1

    if not REPORT_PATH.exists():
        print(f"Intelligence report fixture not found at {REPORT_PATH}")
        return 1

    async with httpx.AsyncClient() as http:
        gen = TravelSafetyScriptGenerator(settings, http)
        # Step through stages individually so a failure in one stage
        # (e.g. Haiku returning malformed scene-breakdown JSON) doesn't
        # hide the script output we want to verify.
        report = gen.load_rhyo_report(REPORT_PATH)
        format_ = gen.select_video_format(report)
        script_text, script_cost = await gen.generate_script(report, format_)
        title, title_cost = await gen.generate_title(report, script_text)
        try:
            description, include_sponsor, desc_cost = await gen.generate_description(
                report, script_text
            )
        except Exception as e:  # description stage may also fail; salvage anyway
            description = f"<description stage failed: {e}>"
            include_sponsor = False
            desc_cost = 0
        destinations = gen.extract_destinations(report, script_text, format_)

    print("=" * 70)
    print("LOCATION     :", report.location_name)
    print("FORMAT       :", format_)
    print("TITLE        :", title)
    print("WORD COUNT   :", len(script_text.split()))
    print("SPONSOR CRD  :", include_sponsor)
    print("SCRIPT COST  :", script_cost)
    print("TITLE COST   :", title_cost)
    print("DESC COST    :", desc_cost)
    print("=" * 70)
    print("FIRST 500 CHARS OF SCRIPT")
    print("-" * 70)
    print(script_text[:500])
    print("=" * 70)
    print("DESCRIPTION")
    print("-" * 70)
    print(description)
    print("=" * 70)
    print("DESTINATIONS")
    print("-" * 70)
    for d in destinations:
        loc = ", ".join(filter(None, [d.poi_name or "", d.city or "", d.region_or_state or "", d.country_code]))
        print(f"  [{d.relevance:9}] {loc}  tags={d.safepath_tags}")
    print("=" * 70)
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
