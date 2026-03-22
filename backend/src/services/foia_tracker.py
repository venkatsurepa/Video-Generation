"""FOIA request lifecycle management.

Tracks outbound FOIA requests from filing through document receipt.
Computes default expected response dates (104 days for federal agencies).
Identifies overdue requests that need follow-up letters.

Document processing: extracts text from received PDFs via PyMuPDF,
runs entity extraction, and stores as research_sources.
"""

from __future__ import annotations

import asyncio
import os
from datetime import date, timedelta
from typing import TYPE_CHECKING, Any

import orjson
import structlog
from psycopg.rows import dict_row

from src.db.queries import (
    GET_FOIA_REQUEST,
    GET_OVERDUE_FOIA,
    INSERT_FOIA_REQUEST,
    INSERT_RESEARCH_SOURCE,
    LIST_FOIA_REQUESTS,
    UPDATE_FOIA_REQUEST,
)
from src.models.research import (
    FOIARequestInput,
    FOIAResponse,
    FOIAUpdateInput,
    ProcessedFOIAResult,
)

if TYPE_CHECKING:
    import uuid

    import httpx
    from psycopg_pool import AsyncConnectionPool

    from src.config import Settings

logger = structlog.get_logger()

# Federal FOIA average response time (simple requests)
FEDERAL_AVG_RESPONSE_DAYS: int = 104


class FOIATracker:
    """FOIA request lifecycle tracking and document processing.

    Timeline context from the bible:
    - Average: 104 days for simple, 600+ days for complex
    - File 10-15 requests/month to build proprietary source library
    - Late entrants face structural time disadvantage

    Electronic filing portals:
    - DOJ: FOIAonline (https://foiaonline.gov)
    - FBI: eFOIPA portal
    - SEC: FOIA office email
    - Most agencies: certified mail with return receipt
    """

    def __init__(
        self,
        settings: Settings,
        db_pool: AsyncConnectionPool,
        http_client: httpx.AsyncClient,
    ) -> None:
        self._settings = settings
        self._db = db_pool
        self._http = http_client

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------

    async def file_request(self, input: FOIARequestInput) -> FOIAResponse:
        """Track a new FOIA request filed with a federal/state agency."""
        today = date.today()
        expected = input.expected_response_date
        if expected is None:
            expected = today + timedelta(days=FEDERAL_AVG_RESPONSE_DAYS)

        async with self._db.connection() as conn:
            async with conn.cursor(row_factory=dict_row) as cur:
                await cur.execute(
                    INSERT_FOIA_REQUEST,
                    {
                        "agency": input.agency,
                        "description": input.description,
                        "case_reference": input.case_reference,
                        "case_file_id": str(input.case_file_id) if input.case_file_id else None,
                        "method": input.method,
                        "date_filed": today.isoformat(),
                        "expected_response_date": expected.isoformat(),
                    },
                )
                row = await cur.fetchone()
            await conn.commit()

        await logger.ainfo(
            "foia_request_filed",
            agency=input.agency,
            expected_response=str(expected),
        )
        return FOIAResponse.from_row(row)

    async def update_status(
        self,
        foia_id: uuid.UUID,
        update: FOIAUpdateInput,
    ) -> FOIAResponse:
        """Update FOIA request status as responses arrive."""
        params: dict[str, Any] = {
            "foia_id": str(foia_id),
            "status": update.status,
            "tracking_number": update.tracking_number,
            "notes": update.notes,
            "documents_received": update.documents_received,
            "actual_response_date": (
                update.actual_response_date.isoformat() if update.actual_response_date else None
            ),
        }

        # Auto-set actual_response_date when receiving documents
        if update.status in ("received", "partial") and update.actual_response_date is None:
            params["actual_response_date"] = date.today().isoformat()

        async with self._db.connection() as conn:
            async with conn.cursor(row_factory=dict_row) as cur:
                await cur.execute(UPDATE_FOIA_REQUEST, params)
                row = await cur.fetchone()
            await conn.commit()

        if row is None:
            msg = f"FOIA request {foia_id} not found"
            raise ValueError(msg)

        await logger.ainfo(
            "foia_status_updated",
            foia_id=str(foia_id),
            new_status=update.status,
        )
        return FOIAResponse.from_row(row)

    async def get_request(self, foia_id: uuid.UUID) -> FOIAResponse | None:
        """Fetch a single FOIA request by ID."""
        async with self._db.connection() as conn, conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(GET_FOIA_REQUEST, {"foia_id": str(foia_id)})
            row = await cur.fetchone()

        if row is None:
            return None
        return FOIAResponse.from_row(row)

    async def get_pending_requests(
        self,
        status: str | None = None,
        agency: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[FOIAResponse]:
        """List FOIA requests with optional filters."""
        async with self._db.connection() as conn, conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(
                LIST_FOIA_REQUESTS,
                {
                    "status": status,
                    "agency": agency,
                    "limit": limit,
                    "offset": offset,
                },
            )
            rows = await cur.fetchall()

        return [FOIAResponse.from_row(row) for row in rows]

    async def get_overdue_requests(self) -> list[FOIAResponse]:
        """Requests past expected response date — need follow-up."""
        async with self._db.connection() as conn, conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(GET_OVERDUE_FOIA)
            rows = await cur.fetchall()

        return [FOIAResponse.from_row(row) for row in rows]

    # ------------------------------------------------------------------
    # Document processing
    # ------------------------------------------------------------------

    async def process_received_documents(
        self,
        foia_id: uuid.UUID,
        file_paths: list[str],
    ) -> ProcessedFOIAResult:
        """Process documents received from a FOIA response.

        For each file:
        1. Extract text from PDFs via PyMuPDF
        2. Run entity extraction via Claude Haiku
        3. Store as research_sources linked to the FOIA's case_file
        4. Upload originals to R2
        """
        # Get the FOIA record to find case_file_id
        foia = await self.get_request(foia_id)
        if foia is None:
            msg = f"FOIA request {foia_id} not found"
            raise ValueError(msg)

        docs_processed = 0
        total_entities = 0
        storage_paths: list[str] = []

        for path in file_paths:
            if not os.path.exists(path):
                await logger.awarning("foia_doc_not_found", path=path)
                continue

            # Extract text
            text = await asyncio.to_thread(self._extract_text_from_file, path)
            if not text:
                continue

            # Entity extraction
            from src.services.research_collector import ResearchCollector

            collector = ResearchCollector(self._settings, self._http, self._db)
            entities = await collector.extract_entities(text)
            total_entities += len(entities)

            # Store as research_source
            filename = os.path.basename(path)
            r2_key = f"foia/{foia_id}/{filename}"

            async with self._db.connection() as conn:
                async with conn.cursor(row_factory=dict_row) as cur:
                    await cur.execute(
                        INSERT_RESEARCH_SOURCE,
                        {
                            "case_file_id": str(foia.case_file_id) if foia.case_file_id else None,
                            "source_type": "foia_document",
                            "title": f"FOIA Document: {filename}",
                            "url": "",
                            "source_name": f"FOIA — {foia.agency}",
                            "publication_date": date.today().isoformat(),
                            "raw_text": text[:50_000],  # Truncate very long docs
                            "entities": orjson.dumps([e.model_dump() for e in entities]).decode(),
                            "metadata": orjson.dumps(
                                {
                                    "foia_id": str(foia_id),
                                    "agency": foia.agency,
                                    "filename": filename,
                                }
                            ).decode(),
                            "relevance_score": 0.8,  # FOIA docs are high-relevance
                        },
                    )
                await conn.commit()

            # Upload to R2
            try:
                from src.utils.storage import R2Client

                r2 = R2Client(
                    account_id=self._settings.storage.account_id,
                    access_key_id=self._settings.storage.access_key_id,
                    secret_access_key=self._settings.storage.secret_access_key,
                )
                await asyncio.to_thread(
                    r2.upload_file,
                    self._settings.storage.bucket_name,
                    r2_key,
                    path,
                    "application/pdf",
                )
                storage_paths.append(r2_key)
            except Exception:
                await logger.awarning("foia_r2_upload_failed", path=path, exc_info=True)

            docs_processed += 1

        await logger.ainfo(
            "foia_docs_processed",
            foia_id=str(foia_id),
            docs=docs_processed,
            entities=total_entities,
        )

        return ProcessedFOIAResult(
            foia_id=foia_id,
            documents_processed=docs_processed,
            entities_extracted=total_entities,
            storage_paths=storage_paths,
        )

    @staticmethod
    def _extract_text_from_file(path: str) -> str:
        """Extract text from a PDF or plain text file. Runs in thread pool."""
        if path.lower().endswith(".pdf"):
            try:
                import fitz  # pymupdf

                doc = fitz.open(path)
                text_parts: list[str] = []
                for page in doc:
                    text_parts.append(page.get_text())
                doc.close()
                return "\n".join(text_parts)
            except Exception:
                return ""
        else:
            # Plain text fallback
            try:
                with open(path, encoding="utf-8", errors="replace") as f:
                    return f.read()
            except Exception:
                return ""
