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
| LLM skill extraction (code, tests) | done |
| dbt models for skills, test runs on 200 postings | done |
| Full extraction run (4,913 open postings, $1.22) | done |
| Daily extraction with a monthly spending limit | done |
| Evaluation (precision, recall) | next |
| Gold tables, Postgres export | planned |
| FastAPI + Next.js app | planned |
| Forecasting | planned |

## Layout

```
config/search.yaml      search terms, cities, API settings
config/skills.yaml      skill list: one name per skill, with category and other spellings
config/llm.yaml         model, prices, monthly spending limit, daily on/off
src/skillradar/         Python package
  config.py             typed loader for config/search.yaml
  ingestion/
    client.py           Jobsuche API client (search, details, retries)
    models.py           API response shapes and refnr checks
    bronze.py           raw data on disk, one folder per day
    snapshot.py         one daily run: search, then details for new postings
    cli.py              command line entry point
  schedule/             daily job on macOS (launchd)
  daily.py              the scheduled job: snapshot, Claude, rebuild silver
  lock.py               stops two runs at the same time
  logs.py               logging setup for all commands
  notify.py             desktop alert when a run fails
  transform/            runs dbt (bronze → silver)
  clean/redact.py       removes emails, phones, links and contact names from texts
  skills/               skill list loader, name lookup, keyword search, report
  extract/              skill extraction with Claude: prompt, batches, spending limit,
                        daily step, quality numbers, silver table rows
  storage.py            atomic writes, private folders, JSON lines
transform/              dbt project
  models/staging/       read bronze JSON and run logs
  models/silver/        postings, locations, daily open postings, history, skills
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

## Skill extraction with Claude

Claude reads each cleaned posting and returns a short, fixed answer: the role, the
seniority, home office, the languages asked for, and the skills (each one required or nice
to have). Postings go out in batches, which cost half price and can take up to a few hours.

Apprenticeships (Ausbildung) are left out: they ask for school grades, not skills.

```sh
uv run skillradar-extract estimate --open-only   # how many postings and what it would cost (free)
uv run skillradar-extract try --refnr <refnr>    # one posting now, to check the answer
uv run skillradar-extract submit --open-only     # send open postings without an answer
uv run skillradar-extract collect                # save the answers of finished batches
uv run skillradar-extract status                 # batches and money spent this month (free)
uv run skillradar-extract quality                # how good the answers look (free)
```

Put your API key in `.env` as `ANTHROPIC_API_KEY` (see `.env.example`). Every answer is
saved with the model and prompt version. When you change either one, postings count as
not done and are sent again.

### Every day

You don't need to run these commands by hand. The daily job (see below) collects finished
batches and sends the new open postings, about 110 a day for about $0.75 a month. Set
`daily: false` in `config/llm.yaml` to turn this off.

### Spending limit

`monthly_budget_usd` in `config/llm.yaml` is the most SkillRadar may spend on Claude in one
calendar month (UTC). It is set to $2.00, about 2 EUR with VAT.

Before anything is sent, SkillRadar adds the worst possible cost to what was spent this
month and only sends what fits. So the limit can't be passed, even if every answer is as
long as allowed. A batch that is still running counts at its worst cost until it is
collected, then at its real cost. When the month's money is used up, the rest waits for
the next month. `status` shows what is left.

### The tables

`skillradar-transform` (and the daily job, after new answers) puts the answers into three
tables. Only answers to the current model and prompt version are used.

| Table | One row per |
|---|---|
| `silver_posting_extractions` | posting: role, seniority, home office |
| `silver_posting_skills` | posting and skill: required, in the skill list, `in_text` |
| `silver_posting_languages` | posting and language: level |

`in_text` says if the posting really names the skill. For a general skill it's fine if it
doesn't ("Networking" for "Netzwerk"). But a product name that isn't in the text was most
likely made up by the model, so leave those out when counting.

`quality` shows, per prompt version: how many answers came back, how often seniority or
home office is `unknown`, skills per posting, how many skills are in `config/skills.yaml`,
and which languages were found. Use it to compare prompt versions before a large run.

## Daily schedule (macOS)

```sh
uv run skillradar-schedule install                   # at login, then every hour
uv run skillradar-schedule install --check-every 30  # check more often
uv run skillradar-schedule run-now                   # start a check now
uv run skillradar-schedule uninstall
```

launchd skips a fixed time when the Mac is off, so the job starts at login and then checks
every hour. Each check runs `skillradar-daily`:

1. **Snapshot**, once per day. Nothing happens when today (UTC) already has a full `ok` or
   `partial` run. A `failed` day is tried again at the next check.
2. **Collect** Claude's finished batches (free).
3. **Rebuild silver** when there are new postings or new answers. A failed build is tried
   again at the next check.
4. **Send** new open postings to Claude, within the monthly limit. Postings that already
   have an answer or are in a running batch are never sent twice.

Problems with Claude (no key, limit reached, API down) are written to the log and never
stop steps 1 and 3. A rejected API key also shows a desktop alert.

While the job runs, `caffeinate` keeps the Mac awake. The log is in
`data/logs/snapshot.log` and only you can read it. You get a desktop alert when a snapshot
is not `ok`.

## Data source

[Jobsuche API](https://github.com/bundesAPI/jobsuche-api) of the Bundesagentur für Arbeit,
public client id `jobboerse-jobsuche` sent as `X-API-Key`. Verified working endpoints:

- search: `GET /pc/v6/jobs?was=…&wo=…&umkreis=…&page=…&size=…`
- details: `GET /pc/v4/jobdetails/{base64(refnr)}` (contains `stellenangebotsBeschreibung`)

The v4 search and v6 details endpoints return 403. The API only lists currently open postings,
so history comes from our own daily snapshots.
