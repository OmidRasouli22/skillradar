"""The CV analysis API. Local only (see security.py).

GET  /api/cv/status           can Claude read CVs, budget left, limits, skill names
POST /api/cv/pdf              the text of a PDF (base64), so the person can check it
POST /api/cv/read             a CV text as a profile, by Claude or by keyword search
POST /api/cv/analyse          a profile compared with the open postings of a role and region
GET  /api/cv/showcases        the example CVs in showcase/cv
GET  /api/cv/showcases/{id}   one example: its text, saved profile and expected results
GET  /api/cv/showcases/{id}/checks   the example's checks run now: passed or not, and why

The CV text is only held while a request runs. Nothing about it is saved or logged.
"""

import base64
import binascii
import logging
import os
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

import anthropic
from dotenv import load_dotenv
from fastapi import APIRouter, Depends, HTTPException
from pydantic import Field

from skillradar.api.labels import REGIONS, ROLES
from skillradar.api.security import local_only, same_page_json
from skillradar.config import PROJECT_ROOT
from skillradar.cv import showcase
from skillradar.cv.families import SkillFamilies
from skillradar.cv.market import MarketCache, NoMarket
from skillradar.cv.match import analyse
from skillradar.cv.profile import CvProfile
from skillradar.cv.reader import (
    MAX_PDF_BYTES,
    MAX_TEXT_CHARS,
    MIN_TEXT_CHARS,
    CvError,
    pdf_text,
    read_with_claude,
    read_with_keywords,
)
from skillradar.extract import budget
from skillradar.extract.schema import Strict
from skillradar.extract.settings import load_settings
from skillradar.extract.store import ExtractionStore
from skillradar.skills.taxonomy import Taxonomy

logger = logging.getLogger(__name__)

# A typical CV with Claude Haiku: about 6,000 tokens in and 3,000 out.
TYPICAL_COST_USD = 0.002
MAX_BASE64 = (MAX_PDF_BYTES + 2) // 3 * 4

ClientFactory = Callable[[], Any]


class PdfRequest(Strict):
    data: str = Field(min_length=8, max_length=MAX_BASE64)


class ReadRequest(Strict):
    text: str = Field(min_length=1, max_length=MAX_TEXT_CHARS * 2)
    mode: Literal["claude", "keywords"]


class AnalyseRequest(Strict):
    profile: CvProfile
    role: str = Field(max_length=40)
    region: str = Field(max_length=40)


def claude_available() -> bool:
    load_dotenv(PROJECT_ROOT / ".env")
    return bool(os.environ.get("ANTHROPIC_API_KEY"))


def cv_router(
    data_dir: Path,
    taxonomy: Taxonomy,
    families: SkillFamilies,
    market: MarketCache,
    showcase_dir: Path = showcase.SHOWCASE_DIR,
    make_client: ClientFactory = anthropic.Anthropic,
) -> APIRouter:
    router = APIRouter(prefix="/api/cv", dependencies=[Depends(local_only)])
    store = ExtractionStore(data_dir / "llm")

    @router.get("/status")
    def status() -> dict:
        settings = load_settings()
        month = budget.month_of(datetime.now(UTC))
        try:
            room = round(max(budget.room_left(settings, store, month), 0.0), 4)
        except budget.OverBudget:
            room = 0.0
        return {
            "claude": claude_available(),
            "model": settings.model,
            "typical_cost_usd": TYPICAL_COST_USD,
            "budget_usd": settings.monthly_budget_usd,
            "room_left_usd": room,
            "limits": {
                "pdf_mb": MAX_PDF_BYTES // 1_000_000,
                "min_chars": MIN_TEXT_CHARS,
                "max_chars": MAX_TEXT_CHARS,
            },
            "skills": taxonomy.names(),
            "roles": [{"id": k, "label": v} for k, v in ROLES.items()],
            "regions": [{"id": k, "label": v} for k, v in REGIONS.items()],
        }

    @router.post("/pdf", dependencies=[Depends(same_page_json)])
    def pdf(body: PdfRequest) -> dict:
        try:
            data = base64.b64decode(body.data, validate=True)
        except (binascii.Error, ValueError) as error:
            raise HTTPException(status_code=422, detail="the file could not be decoded") from error
        try:
            text, pages = pdf_text(data)
        except CvError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error
        return {"text": text, "pages": pages, "chars": len(text)}

    @router.post("/read", dependencies=[Depends(same_page_json)])
    def read(body: ReadRequest) -> dict:
        try:
            if body.mode == "keywords":
                result = read_with_keywords(body.text, taxonomy)
            else:
                if not claude_available():
                    raise HTTPException(
                        status_code=503,
                        detail="no ANTHROPIC_API_KEY in .env; use the quick read instead",
                    )
                result = read_with_claude(
                    make_client(), body.text, load_settings(), taxonomy, store
                )
        except CvError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error
        except budget.OverBudget as error:
            raise HTTPException(status_code=402, detail=str(error)) from error
        except anthropic.AuthenticationError as error:
            raise HTTPException(
                status_code=502, detail="the Claude API key was rejected"
            ) from error
        except anthropic.APIError as error:
            logger.warning("cv: Claude API error %s", type(error).__name__)
            raise HTTPException(
                status_code=502, detail="Claude could not be reached; try again"
            ) from error
        return {
            "mode": body.mode,
            "profile": result.profile.model_dump(),
            "notes": result.notes,
            "cost_usd": result.cost_usd,
        }

    @router.post("/analyse", dependencies=[Depends(same_page_json)])
    def run(body: AnalyseRequest) -> dict:
        if body.role not in ROLES or body.region not in REGIONS:
            raise HTTPException(status_code=422, detail="unknown role or region")
        try:
            current = market.get()
        except NoMarket as error:
            raise HTTPException(status_code=503, detail=str(error)) from error
        year = datetime.now(UTC).year
        return analyse(body.profile, current, families, body.role, body.region, year, taxonomy)

    @router.get("/showcases")
    def showcases() -> list[dict]:
        return [case.summary() for case in showcase.load_all(showcase_dir)]

    def find(case_id: str) -> showcase.Case:
        if not showcase.CASE_ID.fullmatch(case_id):
            raise HTTPException(status_code=422, detail="invalid example id")
        case = showcase.load(showcase_dir, case_id)
        if case is None:
            raise HTTPException(status_code=404, detail="no such example")
        return case

    @router.get("/showcases/{case_id}")
    def one_showcase(case_id: str) -> dict:
        return find(case_id).detail()

    @router.get("/showcases/{case_id}/checks")
    def showcase_checks(case_id: str) -> dict:
        """The saved reading's checks, and the match checks against today's postings."""
        case = find(case_id)
        results = showcase.check_profile(case)
        as_of = None
        if case.profile is not None:
            try:
                current = market.get()
            except NoMarket:
                current = None
            if current is not None:
                target = case.file.target
                year = datetime.now(UTC).year
                analysis = analyse(
                    case.profile, current, families, target.role, target.region, year, taxonomy
                )
                results += showcase.check_match(case, analysis)
                as_of = current.as_of
        return {
            "as_of": as_of,
            "results": [
                {
                    "kind": r.check.kind,
                    "check": showcase.describe(r.check),
                    "why": r.check.why,
                    "passed": r.passed,
                    "actual": r.actual,
                }
                for r in results
            ],
        }

    return router
