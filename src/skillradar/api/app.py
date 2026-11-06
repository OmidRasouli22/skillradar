"""The web API and the page. Local only: it listens on 127.0.0.1.

/api/overview   data date, number of postings, roles and regions to choose from
/api/skills     the most asked-for skills for one role and region
/api/dashboard  everything the page shows for one region
/               the page, built from web/ with `npm run build`
"""

from pathlib import Path
from typing import Annotated

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import JSONResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles

from skillradar.api.data import GoldData, NoData
from skillradar.api.labels import ALL, REGIONS, ROLES
from skillradar.config import DATA_DIR, PROJECT_ROOT
from skillradar.transform.runner import serve_dir

WEB_BUILD = PROJECT_ROOT / "web" / "out"

SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    # The static Next.js page needs inline scripts and styles; nothing loads from elsewhere.
    "Content-Security-Policy": (
        "default-src 'self'; script-src 'self' 'unsafe-inline'; "
        "style-src 'self' 'unsafe-inline'; img-src 'self' data:; frame-ancestors 'none'"
    ),
}


def create_app(data_dir: Path = DATA_DIR, web_build: Path = WEB_BUILD) -> FastAPI:
    gold = GoldData(serve_dir(data_dir))
    app = FastAPI(
        title="SkillRadar", docs_url="/api/docs", redoc_url=None, openapi_url="/api/openapi.json"
    )

    @app.middleware("http")
    async def security_headers(request: Request, call_next):
        response = await call_next(request)
        response.headers.update(SECURITY_HEADERS)
        return response

    @app.exception_handler(NoData)
    async def no_data(request: Request, error: NoData):
        return JSONResponse(status_code=503, content={"detail": str(error)})

    @app.get("/api/overview")
    def overview() -> dict:
        return gold.overview()

    @app.get("/api/skills")
    def skills(
        role: str = ALL,
        region: str = ALL,
        limit: Annotated[int, Query(ge=1, le=50)] = 15,
    ) -> dict:
        if role not in ROLES:
            raise HTTPException(status_code=422, detail=f"unknown role: {role[:40]}")
        if region not in REGIONS:
            raise HTTPException(status_code=422, detail=f"unknown region: {region[:40]}")
        return gold.skills(role, region, limit)

    @app.get("/api/dashboard")
    def dashboard(region: str = ALL) -> dict:
        if region not in REGIONS:
            raise HTTPException(status_code=422, detail=f"unknown region: {region[:40]}")
        return gold.dashboard(region)

    if (web_build / "index.html").exists():
        app.mount("/", StaticFiles(directory=web_build, html=True), name="page")
    else:

        @app.get("/", response_class=PlainTextResponse)
        def page_not_built() -> str:
            return "The page is not built yet: cd web && npm install && npm run build"

    return app
