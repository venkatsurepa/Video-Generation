"""Travel advisory polling from government sources.

Fetches advisories from US State Dept, CDC, WHO, and UK FCDO.
Writes to travel_advisories table and generates Street Level topic candidates
when Level 3-4 advisories are issued or updated.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime
from xml.etree import ElementTree

import httpx

from .base import DiscoveryChannel, DiscoverySource, TopicCandidate

# RSS/API endpoints for advisory sources
ADVISORY_SOURCES = {
    "state_dept": {
        "url": "https://travel.state.gov/_res/rss/TAsTWs.xml",
        "source_key": "state_dept",
        "parser": "_parse_state_dept_rss",
    },
    "cdc": {
        "url": "https://tools.cdc.gov/api/v2/resources/media?topic=travel%20health&contenttype=rss",
        "source_key": "cdc",
        "parser": "_parse_cdc_rss",
    },
    "foreign_office_uk": {
        "url": "https://www.gov.uk/foreign-travel-advice.atom",
        "source_key": "foreign_office_uk",
        "parser": "_parse_fcdo_atom",
    },
}

# Country name → ISO code mapping for advisory parsing
COUNTRY_CODES = {
    "afghanistan": "AF", "albania": "AL", "algeria": "DZ", "argentina": "AR",
    "australia": "AU", "bangladesh": "BD", "brazil": "BR", "cambodia": "KH",
    "cameroon": "CM", "china": "CN", "colombia": "CO", "congo": "CD",
    "costa rica": "CR", "cuba": "CU", "ecuador": "EC", "egypt": "EG",
    "el salvador": "SV", "ethiopia": "ET", "france": "FR", "germany": "DE",
    "greece": "GR", "guatemala": "GT", "haiti": "HT", "honduras": "HN",
    "india": "IN", "indonesia": "ID", "iran": "IR", "iraq": "IQ",
    "israel": "IL", "italy": "IT", "jamaica": "JM", "japan": "JP",
    "jordan": "JO", "kenya": "KE", "lebanon": "LB", "libya": "LY",
    "malaysia": "MY", "mali": "ML", "mexico": "MX", "morocco": "MA",
    "mozambique": "MZ", "myanmar": "MM", "nepal": "NP", "nicaragua": "NI",
    "niger": "NE", "nigeria": "NG", "north korea": "KP", "pakistan": "PK",
    "panama": "PA", "peru": "PE", "philippines": "PH", "russia": "RU",
    "saudi arabia": "SA", "senegal": "SN", "somalia": "SO",
    "south africa": "ZA", "south sudan": "SS", "spain": "ES", "sri lanka": "LK",
    "sudan": "SD", "syria": "SY", "tanzania": "TZ", "thailand": "TH",
    "trinidad and tobago": "TT", "tunisia": "TN", "turkey": "TR",
    "turkiye": "TR", "uganda": "UG", "ukraine": "UA",
    "united kingdom": "GB", "uruguay": "UY", "uzbekistan": "UZ",
    "venezuela": "VE", "vietnam": "VN", "yemen": "YE", "zimbabwe": "ZW",
}


class AdvisoryPoller(DiscoverySource):
    """Polls government travel advisory sources for new/updated advisories."""

    name = "advisory_poller"

    async def scan(self) -> list[TopicCandidate]:
        """Fetch and process advisories from all sources."""
        candidates: list[TopicCandidate] = []

        async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
            for source_name, source_cfg in ADVISORY_SOURCES.items():
                try:
                    resp = await client.get(source_cfg["url"])
                    resp.raise_for_status()
                    parser = getattr(self, source_cfg["parser"])
                    advisories = parser(resp.text, source_cfg["source_key"])
                    saved_advisories = await self._save_advisories(advisories)
                    # Only create topic candidates for high-level advisories
                    for adv in saved_advisories:
                        if adv.get("advisory_level", 0) >= 3:
                            candidates.append(self._advisory_to_candidate(adv))
                    self.logger.info(f"{source_name}: {len(advisories)} parsed, {len(saved_advisories)} new")
                except Exception as e:
                    self.logger.warning(f"Failed to fetch {source_name}: {e}")

        return candidates

    def _parse_state_dept_rss(self, xml_text: str, source_key: str) -> list[dict]:
        """Parse US State Department travel advisory RSS feed."""
        advisories = []
        try:
            root = ElementTree.fromstring(xml_text)
            for item in root.findall(".//item"):
                title = item.findtext("title", "")
                description = item.findtext("description", "")
                link = item.findtext("link", "")
                pub_date = item.findtext("pubDate", "")

                # Extract level from title: "Country - Travel Advisory Level X"
                level_match = re.search(r"Level\s+(\d)", title)
                level = int(level_match.group(1)) if level_match else None

                # Extract country name
                country_name = title.split(" - ")[0].strip() if " - " in title else title.strip()
                country_code = self._country_to_code(country_name)

                advisories.append({
                    "source": source_key,
                    "country_code": country_code or "XX",
                    "country_name": country_name,
                    "advisory_level": level,
                    "advisory_type": self._classify_advisory(description),
                    "title": title[:500],
                    "summary": description[:2000],
                    "url": link,
                    "issued_date": self._parse_date(pub_date),
                    "is_active": True,
                })
        except ElementTree.ParseError as e:
            self.logger.error(f"State Dept RSS parse error: {e}")
        return advisories

    def _parse_cdc_rss(self, xml_text: str, source_key: str) -> list[dict]:
        """Parse CDC travel health notice feed."""
        advisories = []
        try:
            root = ElementTree.fromstring(xml_text)
            for item in root.findall(".//{http://www.w3.org/2005/Atom}entry") or root.findall(".//item"):
                title = (
                    item.findtext("{http://www.w3.org/2005/Atom}title")
                    or item.findtext("title", "")
                )
                summary = (
                    item.findtext("{http://www.w3.org/2005/Atom}summary")
                    or item.findtext("description", "")
                )
                link_el = item.find("{http://www.w3.org/2005/Atom}link")
                link = link_el.get("href", "") if link_el is not None else item.findtext("link", "")

                # CDC uses Watch/Alert/Warning levels
                cdc_level = 1
                title_lower = title.lower()
                if "warning" in title_lower:
                    cdc_level = 3
                elif "alert" in title_lower:
                    cdc_level = 2
                elif "watch" in title_lower:
                    cdc_level = 1

                # Try to extract country
                country_name = self._extract_country_from_text(title)
                country_code = self._country_to_code(country_name) if country_name else "XX"

                advisories.append({
                    "source": source_key,
                    "country_code": country_code,
                    "country_name": country_name or "Global",
                    "advisory_level": cdc_level,
                    "advisory_type": "health",
                    "title": title[:500],
                    "summary": (summary or "")[:2000],
                    "url": link,
                    "issued_date": datetime.now(UTC).strftime("%Y-%m-%d"),
                    "is_active": True,
                })
        except ElementTree.ParseError as e:
            self.logger.error(f"CDC RSS parse error: {e}")
        return advisories

    def _parse_fcdo_atom(self, xml_text: str, source_key: str) -> list[dict]:
        """Parse UK FCDO foreign travel advice Atom feed."""
        advisories = []
        ns = {"atom": "http://www.w3.org/2005/Atom"}
        try:
            root = ElementTree.fromstring(xml_text)
            for entry in root.findall("atom:entry", ns):
                title = entry.findtext("atom:title", "", ns)
                summary = entry.findtext("atom:summary", "", ns)
                link_el = entry.find("atom:link", ns)
                link = link_el.get("href", "") if link_el is not None else ""
                updated = entry.findtext("atom:updated", "", ns)

                # FCDO titles are usually just country names
                country_name = title.strip()
                country_code = self._country_to_code(country_name)

                # FCDO doesn't use numbered levels; we infer from content
                level = 1
                summary_lower = (summary or "").lower()
                if "advise against all travel" in summary_lower:
                    level = 4
                elif "advise against all but essential" in summary_lower:
                    level = 3
                elif "heightened risk" in summary_lower or "increased caution" in summary_lower:
                    level = 2

                advisories.append({
                    "source": source_key,
                    "country_code": country_code or "XX",
                    "country_name": country_name,
                    "advisory_level": level,
                    "advisory_type": self._classify_advisory(summary or ""),
                    "title": f"FCDO: {title}"[:500],
                    "summary": (summary or "")[:2000],
                    "url": link,
                    "issued_date": updated[:10] if updated else datetime.now(UTC).strftime("%Y-%m-%d"),
                    "is_active": True,
                })
        except ElementTree.ParseError as e:
            self.logger.error(f"FCDO Atom parse error: {e}")
        return advisories

    async def _save_advisories(self, advisories: list[dict]) -> list[dict]:
        """Insert new advisories into travel_advisories table. Returns newly inserted rows."""
        new_advisories = []
        for adv in advisories:
            try:
                # Upsert: unique on (source, country_code, issued_date)
                result = self.supabase.table("travel_advisories").upsert(
                    adv, on_conflict="source,country_code,issued_date"
                ).execute()
                if result.data:
                    new_advisories.append(adv)
            except Exception as e:
                self.logger.debug(f"Advisory upsert for {adv.get('country_name')}: {e}")
        return new_advisories

    def _advisory_to_candidate(self, adv: dict) -> TopicCandidate:
        """Convert a high-level advisory into a video topic candidate."""
        level = adv.get("advisory_level", 3)
        country = adv.get("country_name", "Unknown")
        advisory_type = adv.get("advisory_type", "general")

        title_templates = {
            4: f"Do NOT Travel to {country} Right Now — Here's Why",
            3: f"Is {country} Safe? The Advisory Just Changed",
        }
        title = title_templates.get(level, f"{country}: New Travel Advisory Issued")

        return TopicCandidate(
            title=title,
            description=adv.get("summary", "")[:500],
            category="destination_safety",
            channel=DiscoveryChannel.STREET_LEVEL,
            source=adv.get("source", "state_dept"),
            source_url=adv.get("url"),
            raw_signals={
                "advisory_level": level,
                "advisory_type": advisory_type,
                "country_name": country,
            },
            score=min(100, 50 + (level * 12)),  # Level 3 = 86, Level 4 = 98
            country_code=adv.get("country_code"),
        )

    @staticmethod
    def _classify_advisory(text: str) -> str:
        """Classify advisory type from text content."""
        text_lower = text.lower()
        if any(w in text_lower for w in ("terrorism", "terrorist", "extremism")):
            return "terrorism"
        if any(w in text_lower for w in ("crime", "robbery", "kidnap", "carjack")):
            return "crime"
        if any(w in text_lower for w in ("health", "disease", "outbreak", "virus", "epidemic")):
            return "health"
        if any(w in text_lower for w in ("earthquake", "hurricane", "flood", "tsunami")):
            return "natural_disaster"
        if any(w in text_lower for w in ("civil unrest", "protest", "political", "coup", "conflict")):
            return "civil_unrest"
        return "general"

    @staticmethod
    def _country_to_code(name: str) -> str | None:
        """Convert country name to ISO 3166-1 alpha-2 code."""
        if not name:
            return None
        return COUNTRY_CODES.get(name.lower().strip())

    @staticmethod
    def _extract_country_from_text(text: str) -> str | None:
        """Try to find a country name in text."""
        text_lower = text.lower()
        for country in sorted(COUNTRY_CODES.keys(), key=len, reverse=True):
            if country in text_lower:
                return country.title()
        return None

    @staticmethod
    def _parse_date(date_str: str) -> str:
        """Parse various date formats into YYYY-MM-DD."""
        for fmt in ("%a, %d %b %Y %H:%M:%S %z", "%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%d"):
            try:
                return datetime.strptime(date_str.strip(), fmt).strftime("%Y-%m-%d")
            except ValueError:
                continue
        return datetime.now(UTC).strftime("%Y-%m-%d")
