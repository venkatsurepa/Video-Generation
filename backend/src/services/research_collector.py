"""Automated source collection from public federal/state records.

Searches SEC EDGAR, CourtListener/RECAP, DOJ/FBI press releases, FTC
enforcement actions, and Chronicling America (Library of Congress).
Entity extraction uses Claude Haiku for structured NER.

All sources are public domain or freely accessible via published APIs.
"""

from __future__ import annotations

import asyncio
from datetime import date
from typing import TYPE_CHECKING, Any

import httpx
import orjson
import structlog
from psycopg.rows import dict_row

from src.db.queries import (
    GET_CASE_FILE,
    INSERT_CASE_FILE,
    INSERT_RESEARCH_SOURCE,
    UPDATE_CASE_FILE,
)
from src.models.research import (
    CaseFileResponse,
    CollectionRequest,
    CollectionResult,
    CourtCase,
    ExtractedEntity,
    FTCAction,
    NewsArticle,
    PressRelease,
    SECFiling,
)
from src.utils.retry import async_retry

if TYPE_CHECKING:
    import uuid

    from psycopg_pool import AsyncConnectionPool

    from src.config import Settings

logger = structlog.get_logger()

# ---------------------------------------------------------------------------
# API base URLs
# ---------------------------------------------------------------------------

SEC_EFTS_URL: str = "https://efts.sec.gov/LATEST/search-index"
COURTLISTENER_API: str = "https://www.courtlistener.com/api/rest/v4"
DOJ_PRESS_API: str = "https://www.justice.gov/api/v1/press-releases.json"
CHRONICLING_AMERICA_API: str = "https://chroniclingamerica.loc.gov"

# SEC fair-use: identify the app in User-Agent header
SEC_USER_AGENT: str = "CrimeMill/1.0 (research-collector; automated-pipeline)"

# ---------------------------------------------------------------------------
# Concurrency limits
# ---------------------------------------------------------------------------

SEC_CONCURRENCY: int = 10
COURTLISTENER_CONCURRENCY: int = 4
GENERAL_CONCURRENCY: int = 5

# ---------------------------------------------------------------------------
# Entity extraction prompt (Claude Haiku)
# ---------------------------------------------------------------------------

ENTITY_EXTRACTION_SYSTEM: str = """\
You extract structured entities from legal and financial documents.
Return ONLY a JSON array of objects. Each object has these fields:
- entity_type: one of "person", "org", "financial", "date", "location", "legal"
- value: the entity text
- role: contextual role (e.g. "defendant", "prosecutor", "victim", "company", "amount")
- context: short snippet of surrounding text (1 sentence max)

Focus on: names of people, organizations, monetary amounts, key dates,
locations/jurisdictions, legal terms (charges, statutes, case numbers,
verdicts, sentences). Be precise — only extract entities actually present.
"""

# Max characters to send for entity extraction (avoid excessive Haiku cost)
ENTITY_EXTRACTION_MAX_CHARS: int = 15_000


class ResearchCollector:
    """Collects and organizes public records into a searchable case library.

    Sources:
      1. SEC EDGAR — EFTS full-text search for financial filings & enforcement
      2. CourtListener/RECAP — federal court dockets and opinions (free PACER alt)
      3. DOJ — press releases for indictments, charges, sentencing
      4. FTC — enforcement actions and consumer protection cases
      5. Chronicling America — historical newspaper OCR (Library of Congress)

    Entity extraction via Claude Haiku (~$0.001/document).
    """

    def __init__(
        self,
        settings: Settings,
        http_client: httpx.AsyncClient,
        db_pool: AsyncConnectionPool,
    ) -> None:
        self._settings = settings
        self._http = http_client
        self._db = db_pool
        self._sec_sem = asyncio.Semaphore(SEC_CONCURRENCY)
        self._cl_sem = asyncio.Semaphore(COURTLISTENER_CONCURRENCY)
        self._gen_sem = asyncio.Semaphore(GENERAL_CONCURRENCY)

    # ------------------------------------------------------------------
    # Orchestrator
    # ------------------------------------------------------------------

    async def collect(self, request: CollectionRequest) -> CollectionResult:
        """Run parallel searches across requested source types and persist results."""
        await logger.ainfo(
            "research_collect_start",
            query=request.query,
            source_types=request.source_types,
        )

        tasks: list[asyncio.Task[list[dict[str, Any]]]] = []
        types_searched: list[str] = []

        source_dispatch: dict[str, Any] = {
            "sec_filing": lambda: self._collect_sec(
                request.query, request.filing_types, request.date_from
            ),
            "court_document": lambda: self._collect_courtlistener(request.query),
            "doj_press_release": lambda: self._collect_doj(request.query, request.date_from),
            "fbi_press_release": lambda: self._collect_doj(request.query, request.date_from),
            "ftc_action": lambda: self._collect_ftc(request.query),
            "newspaper_article": lambda: self._collect_newspapers(request.query, request.date_from),
        }

        for stype in request.source_types:
            if stype in source_dispatch:
                tasks.append(asyncio.create_task(self._safe(source_dispatch[stype]())))
                types_searched.append(stype)

        all_results: list[list[dict[str, Any]]] = await asyncio.gather(*tasks)

        # Flatten and persist
        flat_sources: list[dict[str, Any]] = []
        for batch in all_results:
            flat_sources.extend(batch)

        stored = await self._persist_sources(flat_sources, request.case_file_id)

        result = CollectionResult(
            sources_found=len(flat_sources),
            sources_stored=stored,
            entities_extracted=0,
            source_types_searched=types_searched,
        )

        await logger.ainfo(
            "research_collect_complete",
            sources_found=result.sources_found,
            sources_stored=result.sources_stored,
        )
        return result

    # ------------------------------------------------------------------
    # SEC EDGAR
    # ------------------------------------------------------------------

    @async_retry(max_attempts=2, base_delay=1.0)
    async def search_sec_edgar(
        self,
        query: str,
        filing_types: list[str] | None = None,
        date_from: date | None = None,
    ) -> list[SECFiling]:
        """Search SEC EDGAR full-text search (EFTS).

        Priority terms: "restatement", "material weakness", "subpoena",
        "cease and desist", "Wells notice".
        """
        async with self._sec_sem:
            params: dict[str, str] = {"q": query}
            if filing_types:
                params["forms"] = ",".join(filing_types)
            if date_from:
                params["dateRange"] = "custom"
                params["startdt"] = date_from.isoformat()

            resp = await self._http.get(
                SEC_EFTS_URL,
                params=params,
                headers={"User-Agent": SEC_USER_AGENT},
                timeout=30.0,
            )
            resp.raise_for_status()
            data = resp.json()

            filings: list[SECFiling] = []
            for hit in data.get("hits", {}).get("hits", []):
                src = hit.get("_source", {})
                try:
                    filings.append(
                        SECFiling(
                            accession_number=src.get("accession_no", ""),
                            company_name=src.get("entity_name", ""),
                            filing_type=src.get("form_type", ""),
                            date_filed=src.get("file_date", "1970-01-01"),
                            url=f"https://www.sec.gov/Archives/edgar/data/"
                            f"{src.get('file_num', '').replace('-', '')}"
                            f"/{src.get('accession_no', '').replace('-', '')}.txt",
                            description=src.get("display_names", [""])[0]
                            if src.get("display_names")
                            else "",
                        )
                    )
                except (ValueError, KeyError):
                    continue

            await logger.ainfo("sec_edgar_results", query=query, count=len(filings))
            return filings

    async def _collect_sec(
        self,
        query: str,
        filing_types: list[str] | None,
        date_from: date | None,
    ) -> list[dict[str, Any]]:
        filings = await self.search_sec_edgar(query, filing_types, date_from)
        return [
            {
                "source_type": "sec_filing",
                "title": f"{f.company_name} — {f.filing_type}",
                "url": f.url,
                "source_name": "SEC EDGAR",
                "publication_date": f.date_filed.isoformat() if f.date_filed else None,
                "raw_text": f.description,
                "metadata": {"accession_number": f.accession_number, "filing_type": f.filing_type},
            }
            for f in filings
        ]

    # ------------------------------------------------------------------
    # CourtListener / RECAP
    # ------------------------------------------------------------------

    @async_retry(max_attempts=2, base_delay=2.0)
    async def search_pacer_recap(
        self,
        query: str,
        court: str | None = None,
        case_type: str | None = None,
    ) -> list[CourtCase]:
        """Search CourtListener/RECAP — free PACER alternative.

        Free registration for API token.  75% of PACER users pay nothing
        (quarterly spending under $30 is waived).
        """
        async with self._cl_sem:
            params: dict[str, str] = {"q": query, "type": "r"}
            if court:
                params["court"] = court
            if case_type:
                params["case_type"] = case_type

            headers: dict[str, str] = {}
            token = self._settings.court_listener.api_token
            if token:
                headers["Authorization"] = f"Token {token}"

            resp = await self._http.get(
                f"{COURTLISTENER_API}/search/",
                params=params,
                headers=headers,
                timeout=30.0,
            )
            resp.raise_for_status()
            data = resp.json()

            cases: list[CourtCase] = []
            for result in data.get("results", []):
                try:
                    cases.append(
                        CourtCase(
                            case_name=result.get("caseName", result.get("case_name", "")),
                            docket_number=result.get(
                                "docketNumber", result.get("docket_number", "")
                            ),
                            court=result.get("court", ""),
                            case_type=result.get("suitNature", ""),
                            date_filed=result.get("dateFiled") or result.get("date_filed"),
                            parties=[
                                p
                                for p in [result.get("plaintiff", ""), result.get("defendant", "")]
                                if p
                            ],
                            document_urls=[
                                result.get("absolute_url", ""),
                            ],
                            source="courtlistener",
                        )
                    )
                except (ValueError, KeyError):
                    continue

            await logger.ainfo("courtlistener_results", query=query, count=len(cases))
            return cases

    async def _collect_courtlistener(self, query: str) -> list[dict[str, Any]]:
        cases = await self.search_pacer_recap(query)
        return [
            {
                "source_type": "court_document",
                "title": c.case_name,
                "url": c.document_urls[0] if c.document_urls else "",
                "source_name": "CourtListener/RECAP",
                "publication_date": c.date_filed.isoformat() if c.date_filed else None,
                "raw_text": f"{c.case_name} | {c.docket_number} | {c.court}",
                "metadata": {
                    "docket_number": c.docket_number,
                    "court": c.court,
                    "parties": c.parties,
                },
            }
            for c in cases
        ]

    # ------------------------------------------------------------------
    # DOJ / FBI Press Releases
    # ------------------------------------------------------------------

    @async_retry(max_attempts=2, base_delay=1.0)
    async def search_doj_press(
        self,
        query: str,
        date_from: date | None = None,
    ) -> list[PressRelease]:
        """Search DOJ press releases — public domain (17 U.S.C. § 105)."""
        async with self._gen_sem:
            params: dict[str, str] = {"keyword": query}
            if date_from:
                params["created_min"] = date_from.isoformat()

            resp = await self._http.get(
                DOJ_PRESS_API,
                params=params,
                timeout=30.0,
            )
            resp.raise_for_status()
            data = resp.json()

            releases: list[PressRelease] = []
            for item in data.get("results", []):
                try:
                    node = item.get("node", item)
                    releases.append(
                        PressRelease(
                            title=node.get("title", ""),
                            agency="DOJ",
                            date=node.get("date", node.get("created", "1970-01-01")),
                            url=node.get("url", node.get("path", "")),
                            summary=node.get("body", node.get("teaser", ""))[:500],
                        )
                    )
                except (ValueError, KeyError):
                    continue

            await logger.ainfo("doj_press_results", query=query, count=len(releases))
            return releases

    async def _collect_doj(self, query: str, date_from: date | None) -> list[dict[str, Any]]:
        releases = await self.search_doj_press(query, date_from)
        return [
            {
                "source_type": "doj_press_release",
                "title": r.title,
                "url": r.url,
                "source_name": f"{r.agency} Press Releases",
                "publication_date": r.date.isoformat() if r.date else None,
                "raw_text": r.summary,
                "metadata": {"agency": r.agency},
            }
            for r in releases
        ]

    # ------------------------------------------------------------------
    # FTC Enforcement Actions
    # ------------------------------------------------------------------

    @async_retry(max_attempts=2, base_delay=1.0)
    async def search_ftc(self, query: str) -> list[FTCAction]:
        """Search FTC enforcement actions and consumer protection cases."""
        async with self._gen_sem:
            # FTC doesn't have a clean JSON API; use their legal library search
            params = {"search_api_fulltext": query, "format": "json"}
            try:
                resp = await self._http.get(
                    "https://www.ftc.gov/legal-library/browse/cases-proceedings",
                    params=params,
                    timeout=30.0,
                    follow_redirects=True,
                )
                resp.raise_for_status()
                data = resp.json()
            except (httpx.HTTPStatusError, orjson.JSONDecodeError, ValueError):
                # FTC site may not return JSON; degrade gracefully
                await logger.awarning("ftc_search_no_json", query=query)
                return []

            actions: list[FTCAction] = []
            for item in data.get("results", data.get("rows", [])):
                try:
                    actions.append(
                        FTCAction(
                            case_name=item.get("title", item.get("case_name", "")),
                            respondent=item.get("respondent", ""),
                            violation_type=item.get("violation_type", ""),
                            url=item.get("url", item.get("path", "")),
                        )
                    )
                except (ValueError, KeyError):
                    continue

            await logger.ainfo("ftc_results", query=query, count=len(actions))
            return actions

    async def _collect_ftc(self, query: str) -> list[dict[str, Any]]:
        actions = await self.search_ftc(query)
        return [
            {
                "source_type": "ftc_action",
                "title": a.case_name,
                "url": a.url,
                "source_name": "FTC",
                "publication_date": a.date.isoformat() if a.date else None,
                "raw_text": f"{a.case_name} | {a.respondent} | {a.violation_type}",
                "metadata": {
                    "respondent": a.respondent,
                    "violation_type": a.violation_type,
                },
            }
            for a in actions
        ]

    # ------------------------------------------------------------------
    # Chronicling America (Library of Congress)
    # ------------------------------------------------------------------

    @async_retry(max_attempts=2, base_delay=1.0)
    async def search_historical_newspapers(
        self,
        query: str,
        date_range: tuple[date, date] | None = None,
    ) -> list[NewsArticle]:
        """Search Chronicling America — 12M+ digitized newspaper pages. Free."""
        async with self._gen_sem:
            params: dict[str, str] = {
                "andtext": query,
                "format": "json",
            }
            if date_range:
                params["dateFilterType"] = "range"
                params["date1"] = date_range[0].strftime("%m/%d/%Y")
                params["date2"] = date_range[1].strftime("%m/%d/%Y")

            resp = await self._http.get(
                f"{CHRONICLING_AMERICA_API}/search/pages/results/",
                params=params,
                timeout=30.0,
            )
            resp.raise_for_status()
            data = resp.json()

            articles: list[NewsArticle] = []
            for item in data.get("items", []):
                try:
                    articles.append(
                        NewsArticle(
                            title=item.get("title", ""),
                            newspaper=item.get("title_normal", item.get("publisher", "")),
                            date=item.get("date"),
                            url=item.get("url", item.get("id", "")),
                            ocr_text=item.get("ocr_eng", "")[:2000],
                            page_info=f"page {item.get('page', '?')}, seq {item.get('sequence', '?')}",
                        )
                    )
                except (ValueError, KeyError):
                    continue

            await logger.ainfo("newspaper_results", query=query, count=len(articles))
            return articles

    async def _collect_newspapers(self, query: str, date_from: date | None) -> list[dict[str, Any]]:
        date_range = None
        if date_from:
            date_range = (date_from, date.today())
        articles = await self.search_historical_newspapers(query, date_range)
        return [
            {
                "source_type": "newspaper_article",
                "title": a.title,
                "url": a.url,
                "source_name": a.newspaper or "Chronicling America",
                "publication_date": a.date.isoformat() if a.date else None,
                "raw_text": a.ocr_text,
                "metadata": {"newspaper": a.newspaper, "page_info": a.page_info},
            }
            for a in articles
        ]

    # ------------------------------------------------------------------
    # State Courts (best-effort)
    # ------------------------------------------------------------------

    async def search_state_courts(
        self,
        query: str,
        state: str,
    ) -> list[CourtCase]:
        """Search state court records — best-effort via CourtListener state filter.

        Full state court API coverage varies widely. CourtListener indexes
        many state courts. For states not covered, returns empty.
        """
        return await self.search_pacer_recap(query, court=state.lower())

    # ------------------------------------------------------------------
    # Entity Extraction (Claude Haiku)
    # ------------------------------------------------------------------

    async def extract_entities(self, text: str) -> list[ExtractedEntity]:
        """Extract structured entities from legal/financial text via Claude Haiku.

        Extracts: people, organizations, financial amounts, dates, locations,
        legal terms (charges, statutes, verdicts, sentences).
        Cost: ~$0.001 per document.
        """
        import anthropic

        if not text.strip():
            return []

        # Truncate to limit cost
        truncated = text[:ENTITY_EXTRACTION_MAX_CHARS]

        client = anthropic.AsyncAnthropic(api_key=self._settings.anthropic.api_key)

        try:
            response = await client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=4096,
                system=ENTITY_EXTRACTION_SYSTEM,
                messages=[{"role": "user", "content": truncated}],
            )
        except Exception:
            await logger.awarning("entity_extraction_failed", exc_info=True)
            return []

        # Parse the JSON array response
        try:
            content = "".join(
                block.text for block in response.content if hasattr(block, "text")
            )
            raw_entities: list[dict[str, str]] = orjson.loads(content)
            return [
                ExtractedEntity(
                    entity_type=e.get("entity_type", "other"),  # type: ignore[arg-type]
                    value=e.get("value", ""),
                    role=e.get("role", ""),
                    context=e.get("context", ""),
                )
                for e in raw_entities
                if e.get("value")
            ]
        except (orjson.JSONDecodeError, KeyError, IndexError):
            await logger.awarning("entity_extraction_parse_failed", exc_info=True)
            return []

    # ------------------------------------------------------------------
    # Case File Builder
    # ------------------------------------------------------------------

    async def build_case_file(
        self,
        case_name: str,
        category: str = "other",
        case_file_id: uuid.UUID | None = None,
    ) -> CaseFileResponse:
        """Aggregate all sources for a case into a single CaseFile record.

        1. Create or retrieve case_files record
        2. Run collect() across all source types
        3. Extract entities from collected text
        4. Aggregate entities and build timeline
        5. Update case file with results
        """
        await logger.ainfo("build_case_file_start", case_name=case_name)

        # Step 1: Create or fetch case file
        if case_file_id is None:
            async with self._db.connection() as conn:
                async with conn.cursor(row_factory=dict_row) as cur:
                    await cur.execute(
                        INSERT_CASE_FILE,
                        {
                            "case_name": case_name,
                            "category": category,
                            "summary": "",
                        },
                    )
                    row = await cur.fetchone()
                await conn.commit()
            case_file_id = row["id"]

        # Step 2: Collect from all sources
        collection = await self.collect(
            CollectionRequest(
                query=case_name,
                case_file_id=case_file_id,
                source_types=[
                    "sec_filing",
                    "court_document",
                    "doj_press_release",
                    "ftc_action",
                    "newspaper_article",
                ],
            )
        )

        # Step 3: Extract entities from all collected text
        all_entities: list[ExtractedEntity] = []
        async with self._db.connection() as conn, conn.cursor(row_factory=dict_row) as cur:
            from src.db.queries import GET_CASE_SOURCES

            await cur.execute(GET_CASE_SOURCES, {"case_file_id": str(case_file_id)})
            source_rows = await cur.fetchall()

        entity_tasks = [
            self._safe(self.extract_entities(row["raw_text"]))
            for row in source_rows
            if row.get("raw_text")
        ]
        if entity_tasks:
            entity_batches = await asyncio.gather(*entity_tasks)
            for batch in entity_batches:
                all_entities.extend(batch)

        # Step 4: Build timeline from source dates
        timeline: list[dict[str, str]] = []
        for row in source_rows:
            if row.get("publication_date"):
                timeline.append(
                    {
                        "date": str(row["publication_date"]),
                        "event": row.get("title", ""),
                        "source_type": row.get("source_type", ""),
                    }
                )
        timeline.sort(key=lambda x: x.get("date", ""))

        # Step 5: Update case file
        entities_json = orjson.dumps([e.model_dump() for e in all_entities]).decode()
        timeline_json = orjson.dumps(timeline).decode()

        async with self._db.connection() as conn:
            async with conn.cursor(row_factory=dict_row) as cur:
                await cur.execute(
                    UPDATE_CASE_FILE,
                    {
                        "case_file_id": str(case_file_id),
                        "case_name": None,
                        "category": None,
                        "summary": None,
                        "key_entities": entities_json,
                        "timeline": timeline_json,
                        "financial_impact_usd": None,
                        "status": None,
                        "assigned_video_id": None,
                        "assigned_topic_id": None,
                        "notes": None,
                    },
                )
            await conn.commit()

        # Fetch the final result
        async with self._db.connection() as conn, conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(GET_CASE_FILE, {"case_file_id": str(case_file_id)})
            final_row = await cur.fetchone()

        await logger.ainfo(
            "build_case_file_complete",
            case_name=case_name,
            sources=collection.sources_stored,
            entities=len(all_entities),
        )
        return CaseFileResponse.from_row(final_row)

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    async def _persist_sources(
        self,
        sources: list[dict[str, Any]],
        case_file_id: uuid.UUID | None = None,
    ) -> int:
        """Insert collected sources into research_sources table."""
        if not sources:
            return 0

        stored = 0
        async with self._db.connection() as conn:
            async with conn.cursor(row_factory=dict_row) as cur:
                for source in sources:
                    try:
                        await cur.execute(
                            INSERT_RESEARCH_SOURCE,
                            {
                                "case_file_id": str(case_file_id) if case_file_id else None,
                                "source_type": source.get("source_type", "other"),
                                "title": source.get("title", ""),
                                "url": source.get("url", ""),
                                "source_name": source.get("source_name", ""),
                                "publication_date": source.get("publication_date"),
                                "raw_text": source.get("raw_text", ""),
                                "entities": orjson.dumps(source.get("entities", [])).decode(),
                                "metadata": orjson.dumps(source.get("metadata", {})).decode(),
                                "relevance_score": source.get("relevance_score", 0),
                            },
                        )
                        stored += 1
                    except Exception:
                        await logger.awarning(
                            "persist_source_failed",
                            title=source.get("title"),
                            exc_info=True,
                        )
            await conn.commit()

        return stored

    # ------------------------------------------------------------------
    # DB read helpers (for API routes)
    # ------------------------------------------------------------------

    async def get_case_file(self, case_file_id: uuid.UUID) -> dict[str, Any] | None:
        async with self._db.connection() as conn, conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(GET_CASE_FILE, {"case_file_id": str(case_file_id)})
            return await cur.fetchone()

    async def list_case_files(
        self,
        category: str | None = None,
        status: str | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        from src.db.queries import LIST_CASE_FILES

        async with self._db.connection() as conn, conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(
                LIST_CASE_FILES,
                {
                    "category": category,
                    "status": status,
                    "limit": limit,
                    "offset": offset,
                },
            )
            return await cur.fetchall()

    async def search_sources(
        self,
        query: str,
        source_type: str | None = None,
        date_from: date | None = None,
        date_to: date | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        from src.db.queries import SEARCH_RESEARCH_SOURCES

        async with self._db.connection() as conn, conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(
                SEARCH_RESEARCH_SOURCES,
                {
                    "query": query,
                    "source_type": source_type,
                    "date_from": date_from.isoformat() if date_from else None,
                    "date_to": date_to.isoformat() if date_to else None,
                    "limit": limit,
                    "offset": offset,
                },
            )
            return await cur.fetchall()

    # ------------------------------------------------------------------
    # Error isolation
    # ------------------------------------------------------------------

    @staticmethod
    async def _safe(coro: Any) -> list[Any]:
        """Run a coroutine and return [] on any exception."""
        try:
            result: list[Any] = await coro
            return result
        except Exception:
            await logger.awarning("research_source_failed", exc_info=True)
            return []
