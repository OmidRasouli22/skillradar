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
| Daily snapshot (bronze) | next |
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
    models.py           API response shapes
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

## Data source

[Jobsuche API](https://github.com/bundesAPI/jobsuche-api) of the Bundesagentur für Arbeit,
public client id `jobboerse-jobsuche` sent as `X-API-Key`. Verified working endpoints:

- search: `GET /pc/v6/jobs?was=…&wo=…&umkreis=…&page=…&size=…`
- details: `GET /pc/v4/jobdetails/{base64(refnr)}` (contains `stellenangebotsBeschreibung`)

The v4 search and v6 details endpoints return 403. The API only lists currently open postings,
so history comes from our own daily snapshots.
