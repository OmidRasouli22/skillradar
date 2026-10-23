import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

from skillradar.ingestion.models import Posting

FIXTURES = Path(__file__).parent / "fixtures"


def load_fixture(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def posting(refnr: object) -> Posting:
    return {"referenznummer": refnr, "stellenangebotsTitel": "Data Engineer"}


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


class FakeClock:
    """Starts at a fixed UTC time and moves one second per call."""

    def __init__(self, start: datetime = datetime(2026, 10, 23, 6, 0, tzinfo=UTC)) -> None:
        self.now = start

    def __call__(self) -> datetime:
        current = self.now
        self.now += timedelta(seconds=1)
        return current


class FakeSource:
    """Stands in for JobsucheClient. Values that are exceptions get raised."""

    def __init__(self, searches=None, details=None) -> None:
        self.searches = searches or {}
        self.details_map = details or {}
        self.details_calls: list[str] = []

    def __enter__(self) -> "FakeSource":
        return self

    def __exit__(self, *_: object) -> None:
        pass

    def search(self, term, city, radius_km):
        result = self.searches.get((term, city), [])
        if isinstance(result, Exception):
            raise result
        return iter(result)

    def details(self, refnr):
        self.details_calls.append(refnr)
        default = {"referenznummer": refnr, "stellenangebotsBeschreibung": "SQL, Python"}
        result = self.details_map.get(refnr, default)
        if isinstance(result, Exception):
            raise result
        return result
