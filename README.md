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
| Daily schedule | done |
| Silver postings (dbt + DuckDB) | done |
| History: first/last seen | next |
| Remove personal data | planned |
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
  schedule/             daily job on macOS (launchd)
  lock.py               stops two runs at the same time
  notify.py             desktop alert when a run fails
  transform/            runs dbt (bronze → silver)
transform/              dbt project
  models/staging/       read bronze JSON, newest record per posting
  models/silver/        silver_postings, silver_posting_locations
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

## Silver tables

```sh
uv run skillradar-transform                            # build and test all models
uv run skillradar-transform --select silver_postings   # one model
```

dbt reads the bronze files and writes tables to `data/warehouse.duckdb`. Each build also runs
the data tests in `transform/`, so a broken table stops the build.

| Table | One row per |
|---|---|
| `silver_postings` | posting: title, employer, type, salary, home office, first published date, description |
| `silver_posting_locations` | posting and place (a posting can list up to 10 places) |

## Daily schedule (macOS)

```sh
uv run skillradar-schedule install            # every day at 06:00
uv run skillradar-schedule install --hour 7   # another time
uv run skillradar-schedule run-now            # start the job once, now
uv run skillradar-schedule uninstall
```

The log is in `data/logs/snapshot.log`. You get a desktop alert when a run is not `ok`.
If the Mac sleeps at 06:00, the run starts when it wakes up. If it is off, that day is
skipped.

## Data source

[Jobsuche API](https://github.com/bundesAPI/jobsuche-api) of the Bundesagentur für Arbeit,
public client id `jobboerse-jobsuche` sent as `X-API-Key`. Verified working endpoints:

- search: `GET /pc/v6/jobs?was=…&wo=…&umkreis=…&page=…&size=…`
- details: `GET /pc/v4/jobdetails/{base64(refnr)}` (contains `stellenangebotsBeschreibung`)

The v4 search and v6 details endpoints return 403. The API only lists currently open postings,
so history comes from our own daily snapshots.
