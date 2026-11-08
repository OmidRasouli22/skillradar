"""The web API and the page. Local only: it listens on 127.0.0.1.

/api/overview   data date, number of postings, roles and regions to choose from
/api/skills     the most asked-for skills for one role and region
/api/dashboard  everything the page shows for one region
/api/postings   open postings for a role and region, newest first
/api/postings/{refnr}  one posting with the important parts marked
/api/labels     the review page for the evaluation labels (see labeling.py)
/api/health     pipeline health: freshness, runs, tests, Claude cost, coverage
/api/cv         the CV analysis, shown on the start page (see cv.py)
/               the page, built from web/ with `npm run build`
/label          the review page
/health         the health page
"""

from pathlib import Path
from typing import Annotated

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles

from skillradar.api.cv import ClientFactory, cv_router
from skillradar.api.data import GoldData, NoData
from skillradar.api.labeling import labeling_router
from skillradar.api.labels import ALL, REGIONS, ROLES
from skillradar.api.postings import REFNR
from skillradar.config import DATA_DIR, PROJECT_ROOT
from skillradar.cv.families import load_families
from skillradar.cv.market import MarketCache
from skillradar.cv.reader import make_client as make_cv_client
from skillradar.cv.showcase import SHOWCASE_DIR
from skillradar.evaluate.labels import LABELS_PATH, LabelStore
from skillradar.health import build_health
from skillradar.skills.taxonomy import load_taxonomy
from skillradar.transform.runner import serve_dir

WEB_BUILD = PROJECT_ROOT / "web" / "out"
# Pages besides the start page. The static build writes them as <name>.html.
PAGES = ("label", "health")

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


def create_app(
    data_dir: Path = DATA_DIR,
    web_build: Path = WEB_BUILD,
    labels: Path = LABELS_PATH,
    showcases: Path = SHOWCASE_DIR,
    make_client: ClientFactory = make_cv_client,
) -> FastAPI:
    taxonomy = load_taxonomy()
    gold = GoldData(serve_dir(data_dir), taxonomy)
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
        _check(role, region)
        return gold.skills(role, region, limit)

    @app.get("/api/dashboard")
    def dashboard(region: str = ALL) -> dict:
        if region not in REGIONS:
            raise HTTPException(status_code=422, detail=f"unknown region: {region[:40]}")
        return gold.dashboard(region)

    @app.get("/api/postings")
    def postings(
        role: str = ALL,
        region: str = ALL,
        offset: Annotated[int, Query(ge=0, le=100_000)] = 0,
        limit: Annotated[int, Query(ge=1, le=50)] = 20,
    ) -> dict:
        _check(role, region)
        return gold.postings(role, region, offset, limit)

    @app.get("/api/postings/{refnr}")
    def posting(refnr: str) -> dict:
        if not REFNR.fullmatch(refnr):
            raise HTTPException(status_code=422, detail="invalid reference number")
        found = gold.posting(refnr)
        if found is None:
            raise HTTPException(status_code=404, detail="no open posting with this number")
        return found

    @app.get("/api/health")
    def health() -> dict:
        return build_health(data_dir)

    app.include_router(labeling_router(LabelStore(labels), data_dir, taxonomy))
    app.include_router(
        cv_router(
            data_dir,
            taxonomy,
            load_families(taxonomy),
            MarketCache(serve_dir(data_dir), taxonomy),
            showcases,
            make_client,
        )
    )

    for page in PAGES:
        if (web_build / f"{page}.html").exists():
            _page_route(app, page, web_build / f"{page}.html")

    if (web_build / "index.html").exists():
        app.mount("/", StaticFiles(directory=web_build, html=True), name="page")
    else:

        @app.get("/", response_class=PlainTextResponse)
        def page_not_built() -> str:
            return "The page is not built yet: cd web && npm install && npm run build"

    return app


def _page_route(app: FastAPI, page: str, file: Path) -> None:
    # HEAD too: the page's links ask with HEAD whether a page exists before they open it.
    @app.api_route(f"/{page}", methods=["GET", "HEAD"], include_in_schema=False)
    def serve() -> FileResponse:
        return FileResponse(file)


def _check(role: str, region: str) -> None:
    if role not in ROLES:
        raise HTTPException(status_code=422, detail=f"unknown role: {role[:40]}")
    if region not in REGIONS:
        raise HTTPException(status_code=422, detail=f"unknown region: {region[:40]}")
