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
| History: first/last seen | done |
| Remove personal data, clean city names | done |
| Run once a day when the Mac is on, compress search files | done |
| Skill list (taxonomy) + keyword baseline | done |
| LLM skill extraction | next |
| Evaluation (precision, recall) | planned |
| Gold tables, Postgres export | planned |
| FastAPI + Next.js app | planned |
| Forecasting | planned |

## Layout

```
config/search.yaml      search terms, cities, API settings
config/skills.yaml      skill list: one name per skill, with category and other spellings
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
  clean/redact.py       removes emails, phones, links and contact names from texts
  skills/               skill list loader, name lookup, keyword search, report
transform/              dbt project
  models/staging/       read bronze JSON and run logs
  models/silver/        postings, locations, daily open postings, history
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
search/snapshot_date=YYYY-MM-DD/run_<id>.jsonl.gz every search result, with term and city (gzip)
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
| `silver_postings` | posting: title, employer, type, salary, home office, first published date |
| `silver_posting_texts` | posting: description without personal data |
| `silver_posting_locations` | posting and place, with cleaned city name (a posting can list up to 10 places) |
| `silver_posting_days` | posting and day it was open in our snapshots |
| `silver_posting_history` | posting: first seen, last seen, days seen, closed on |

Descriptions often name a contact person with phone and email. `silver_posting_texts`
replaces these with `[name]`, `[phone]`, `[email]` and `[link]`. The raw text stays only in
bronze on this machine. The rules do not use a name model, because a name model would also
remove skills like "Kafka".

A posting counts as closed on the first *complete* day it is missing. A day is complete when
it has an `ok` run over all cities and terms. Partial runs and test runs with `--city` or
`--term` never close postings, because a missing posting may only have been missed.

## Skills

`config/skills.yaml` maps every spelling of a skill to one name ("PySpark" → Spark,
"K8s" → Kubernetes). Names that are also normal words ("REST", "Go") are marked
`ambiguous`; the keyword search then only uses their safe spellings ("REST-API", "Golang").

```sh
uv run skillradar-skills report                         # most common skills in all postings
uv run skillradar-skills report --title "Data Engineer"  # only matching titles
```

The keyword search is a simple baseline. The LLM extraction has to beat it.

## Daily schedule (macOS)

```sh
uv run skillradar-schedule install                   # at login, then every hour
uv run skillradar-schedule install --check-every 30  # check more often
uv run skillradar-schedule run-now                   # start a check now
uv run skillradar-schedule uninstall
```

launchd skips a fixed time when the Mac is off, so the job starts at login and then checks
every hour. With `--once-per-day` the snapshot does nothing when today (UTC) already has a
full `ok` or `partial` run. A `failed` day is tried again at the next check. While a run is
going, `caffeinate` keeps the Mac awake.

The log is in `data/logs/snapshot.log`. You get a desktop alert when a run is not `ok`.

## Data source

[Jobsuche API](https://github.com/bundesAPI/jobsuche-api) of the Bundesagentur für Arbeit,
public client id `jobboerse-jobsuche` sent as `X-API-Key`. Verified working endpoints:

- search: `GET /pc/v6/jobs?was=…&wo=…&umkreis=…&page=…&size=…`
- details: `GET /pc/v4/jobdetails/{base64(refnr)}` (contains `stellenangebotsBeschreibung`)

The v4 search and v6 details endpoints return 403. The API only lists currently open postings,
so history comes from our own daily snapshots.
