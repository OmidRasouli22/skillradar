"""Command line: uv run skillradar-publish [--dry-run]

Builds the public site in data/site (the static page plus fresh data) and pushes it to
the GitHub Pages branch. --dry-run builds it without pushing, to look at it first.
The page itself is built with `npm run build:public` in web/, only when it changes.
"""

import argparse
import logging
import shutil
import sys
from datetime import UTC, datetime
from pathlib import Path

import yaml
from pydantic import BaseModel, Field

from skillradar.api.data import GoldData, NoData
from skillradar.config import DATA_DIR, PROJECT_ROOT
from skillradar.health import build_health
from skillradar.logs import setup_logging
from skillradar.publish.git import PublishError, push, remote_url
from skillradar.publish.site import export_data, write_health
from skillradar.skills.taxonomy import load_taxonomy
from skillradar.transform.runner import serve_dir

logger = logging.getLogger(__name__)

SITE_CONFIG = PROJECT_ROOT / "config" / "site.yaml"
PUBLIC_PAGE = PROJECT_ROOT / "web" / "out-public"


class SiteSettings(BaseModel):
    enabled: bool
    remote: str = Field(pattern=r"^[A-Za-z0-9._-]{1,50}$")
    branch: str = Field(pattern=r"^[A-Za-z0-9._/-]{1,50}$")


def load_site_settings(path: Path = SITE_CONFIG) -> SiteSettings:
    with path.open(encoding="utf-8") as f:
        return SiteSettings.model_validate(yaml.safe_load(f))


def site_dir(data_dir: Path) -> Path:
    return data_dir / "site"


def marker(data_dir: Path) -> Path:
    """Touched after each successful push."""
    return data_dir / ".site-published"


def needs_publish(data_dir: Path) -> bool:
    """True if the gold data changed after the last push."""
    files = list(serve_dir(data_dir).glob("*.parquet"))
    if not files:
        return False
    if not marker(data_dir).exists():
        return True
    return max(f.stat().st_mtime for f in files) > marker(data_dir).stat().st_mtime


def daily_publish(data_dir: Path) -> None:
    """The daily job's step: push the site when it is on and the data changed."""
    settings = load_site_settings()
    if not settings.enabled:
        logger.info("site publishing is off (enabled in config/site.yaml)")
        return
    if not needs_publish(data_dir):
        logger.info("site is up to date")
        return
    publish(data_dir, settings)
    marker(data_dir).touch()


def build_site(data_dir: Path) -> tuple[Path, dict[str, int]]:
    """A fresh site folder: the built page plus the data files."""
    page = PUBLIC_PAGE
    if not (page / "index.html").exists():
        raise PublishError("build the public page first: cd web && npm run build:public")
    site = site_dir(data_dir)
    if site.exists():
        shutil.rmtree(site)
    shutil.copytree(page, site)
    counts = export_data(GoldData(serve_dir(data_dir), load_taxonomy()), site)
    write_health(build_health(data_dir), site)
    # GitHub Pages runs Jekyll by default, which hides folders like _next.
    (site / ".nojekyll").touch()
    return site, counts


def publish(data_dir: Path, settings: SiteSettings, dry_run: bool = False) -> Path:
    site, counts = build_site(data_dir)
    logger.info(
        "site built: %d regions, %d job lists, %d jobs in %s",
        counts["regions"], counts["lists"], counts["jobs"], site,
    )  # fmt: skip
    if dry_run:
        return site
    url = remote_url(PROJECT_ROOT, settings.remote)
    today = datetime.now(UTC).date().isoformat()
    push(site, url, settings.branch, f"Site data {today}")
    logger.info("site pushed to %s (branch %s)", settings.remote, settings.branch)
    return site


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Publish the public site to GitHub Pages.")
    parser.add_argument("--data-dir", type=Path, default=DATA_DIR)
    parser.add_argument("--dry-run", action="store_true", help="build the site, do not push")
    args = parser.parse_args(argv)
    setup_logging()
    data_dir = args.data_dir.resolve()
    try:
        site = publish(data_dir, load_site_settings(), args.dry_run)
    except (PublishError, NoData) as error:
        print(error, file=sys.stderr)
        return 1
    if not args.dry_run:
        marker(data_dir).touch()
    if args.dry_run:
        print(f"built {site} (not pushed). To look at it: cd {site} && python3 -m http.server")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
