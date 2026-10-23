# SkillRadar

Which skills do German tech employers ask for, and which ones are you missing?

SkillRadar collects job postings from the Bundesagentur für Arbeit every day, extracts the
required skills with an LLM, keeps the history, and shows skill demand and trends per role and
region. A CV gap analyser compares your CV with that demand.

## Status

| Part | State |
|---|---|
| Project foundation | done |
| BA API client | done |
| Daily snapshot (bronze) | done |
| Daily schedule | next |
| Silver layer, history tracking | planned |
| LLM skill extraction + eval | planned |
| Gold tables, Postgres export | planned |
| FastAPI + Next.js app | planned |
| Forecasting | planned |

## Layout

```
config/search.yaml      search terms, cities, API settings
src/skillradar/         Python package
  config.py             typed loader for config/search.yaml
  ingestion/
    client.py           Jobsuche API client (search, details, retries)
    models.py           API response shapes and refnr checks
    bronze.py           raw data on disk, one folder per day
    snapshot.py         one daily run: search, then details for new postings
    cli.py              command line entry point
tests/                  unit tests, no network needed
  fixtures/             saved API responses
data/                   local snapshots (git-ignored)
```

## Setup

Requires [uv](https://docs.astral.sh/uv/).

```sh
uv sync
uv run pytest
uv run ruff check .
```

## Daily snapshot

```sh
uv run skillradar-snapshot                                  # all terms and cities
uv run skillradar-snapshot --city Stuttgart --term Python   # a small test run
```

Data goes to `data/bronze/`:

```
search/snapshot_date=YYYY-MM-DD/run_<id>.jsonl    every search result, with term and city
details/snapshot_date=YYYY-MM-DD/run_<id>.jsonl   full posting, fetched once per refnr
runs/run_<id>.json                                counts, errors and status of the run
```

A run is `ok`, `partial` (some requests failed) or `failed` (no search worked). Failed
details are not saved, so the next run tries them again.

## Data source

[Jobsuche API](https://github.com/bundesAPI/jobsuche-api) of the Bundesagentur für Arbeit,
public client id `jobboerse-jobsuche` sent as `X-API-Key`. Verified working endpoints:

- search: `GET /pc/v6/jobs?was=…&wo=…&umkreis=…&page=…&size=…`
- details: `GET /pc/v4/jobdetails/{base64(refnr)}` (contains `stellenangebotsBeschreibung`)

The v4 search and v6 details endpoints return 403. The API only lists currently open postings,
so history comes from our own daily snapshots.
