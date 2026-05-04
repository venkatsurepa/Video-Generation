"""GDELT news monitoring wrapper.

Wraps the existing gdeltdoc integration from topic_selector.py
into the discovery source interface. Scans GDELT's global news
archive for trending crime and travel safety stories.

Requires: pip install gdeltdoc
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from .base import DiscoveryChannel, DiscoverySource, TopicCandidate

# Crime keywords for GDELT article search
CRIME_KEYWORDS = frozenset({
    "fraud", "ponzi scheme", "embezzlement", "money laundering",
    "insider trading", "corruption indictment", "SEC charges",
    "financial crime conviction", "cybercrime arrest",
    "murder conviction", "serial killer", "cold case solved",
    "wrongful conviction exonerated", "heist robbery",
    "organized crime bust", "drug trafficking arrest",
    "kidnapping rescue", "human trafficking",
})

# Travel safety keywords for GDELT
TRAVEL_KEYWORDS = frozenset({
    "tourist killed", "tourist robbed", "tourist kidnapped",
    "travel warning", "travel advisory", "tourist scam",
    "tourist attacked", "tourist arrested",
    "embassy evacuation", "civil unrest tourists",
    "natural disaster tourism", "terrorist attack tourist",
})


class GdeltScanner(DiscoverySource):
    """Scans GDELT global news archive for trending crime and travel stories."""

    name = "gdelt"

    async def scan(self) -> list[TopicCandidate]:
        """Search GDELT for recent crime and travel safety news."""
        try:
            from gdeltdoc import Filters, GdeltDoc
        except ImportError:
            self.logger.warning("gdeltdoc not installed — pip install gdeltdoc")
            return []

        candidates: list[TopicCandidate] = []
        gd = GdeltDoc()

        # Date range: last 7 days
        end_date = datetime.now(UTC)
        start_date = end_date - timedelta(days=7)
        start_str = start_date.strftime("%Y-%m-%d")
        end_str = end_date.strftime("%Y-%m-%d")

        # Scan crime keywords
        for keyword in CRIME_KEYWORDS:
            try:
                f = Filters(
                    keyword=keyword,
                    start_date=start_str,
                    end_date=end_str,
                    num_records=10,
                    country="US",
                )
                articles = gd.article_search(f)
                if articles is not None and not articles.empty:
                    for _, row in articles.head(3).iterrows():
                        title = str(row.get("title", ""))
                        url = str(row.get("url", ""))
                        domain = str(row.get("domain", ""))
                        seendate = str(row.get("seendate", ""))

                        if len(title) < 20:
                            continue

                        candidates.append(TopicCandidate(
                            title=title[:200],
                            description=f"GDELT article from {domain}. Keyword: {keyword}. Date: {seendate}",
                            category=self._keyword_to_category(keyword),
                            channel=DiscoveryChannel.CRIMEMILL,
                            source="gdelt",
                            source_url=url,
                            raw_signals={
                                "keyword": keyword,
                                "domain": domain,
                                "seen_date": seendate,
                            },
                            score=50,  # Base score, refined by scorer
                        ))
            except Exception as e:
                self.logger.debug(f"GDELT search failed for '{keyword}': {e}")

        # Scan travel keywords
        for keyword in TRAVEL_KEYWORDS:
            try:
                f = Filters(
                    keyword=keyword,
                    start_date=start_str,
                    end_date=end_str,
                    num_records=10,
                )
                articles = gd.article_search(f)
                if articles is not None and not articles.empty:
                    for _, row in articles.head(3).iterrows():
                        title = str(row.get("title", ""))
                        url = str(row.get("url", ""))
                        domain = str(row.get("domain", ""))

                        if len(title) < 20:
                            continue

                        candidates.append(TopicCandidate(
                            title=title[:200],
                            description=f"GDELT travel safety article from {domain}. Keyword: {keyword}.",
                            category="destination_safety",
                            channel=DiscoveryChannel.STREET_LEVEL,
                            source="gdelt",
                            source_url=url,
                            raw_signals={"keyword": keyword, "domain": domain},
                            score=50,
                        ))
            except Exception as e:
                self.logger.debug(f"GDELT travel search failed for '{keyword}': {e}")

        self.logger.info(f"GDELT scan found {len(candidates)} candidates")
        return candidates

    @staticmethod
    def _keyword_to_category(keyword: str) -> str:
        """Map GDELT keyword to case_files category."""
        kw = keyword.lower()
        if "fraud" in kw or "embezzlement" in kw or "sec charges" in kw:
            return "corporate_fraud"
        if "ponzi" in kw:
            return "ponzi_scheme"
        if "laundering" in kw:
            return "white_collar"
        if "insider trading" in kw:
            return "corporate_fraud"
        if "corruption" in kw:
            return "government_corruption"
        if "cybercrime" in kw:
            return "cybercrime"
        if "murder" in kw:
            return "murder"
        if "serial killer" in kw:
            return "serial_killer"
        if "cold case" in kw:
            return "cold_case"
        if "wrongful" in kw:
            return "wrongful_conviction"
        if "heist" in kw or "robbery" in kw:
            return "heist"
        if "organized crime" in kw:
            return "organized_crime"
        if "trafficking" in kw:
            return "drug_trafficking"
        if "kidnapping" in kw:
            return "kidnapping"
        return "other"
