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
| Gold tables (skill demand per role and region) | done |
| Webpage: one page, local (FastAPI + Next.js) | done |
| Public website on GitHub Pages, updated daily | done |
| Skill trends over time | planned |
| Evaluation (precision, recall) | planned |
| Postgres export, hosting | planned |
| Forecasting | planned |

## Layout

```
config/search.yaml      search terms, cities, API settings
config/skills.yaml      skill list: one name per skill, with category and other spellings
config/llm.yaml         model, prices, monthly spending limit, daily on/off
config/site.yaml        public website: on/off, git remote and branch
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
  api/                  web API over the gold tables, and the command that starts the page
  publish/              the public website: data files and the push to GitHub Pages
  storage.py            atomic writes, private folders, JSON lines
web/                    the page (Next.js), built into static files in web/out
transform/              dbt project
  models/staging/       read bronze JSON and run logs
  models/silver/        postings, locations, daily open postings, history, skills
  models/gold/          skill demand and shares per role and region, for the webpage
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

`config/skills.yaml` is the list of about 310 skills. It maps every spelling of a skill to
one name ("PySpark" → Spark, "K8s" → Kubernetes). Two marks matter:

- `general`: the skill is a concept, not a product ("Networking", "CI/CD"). Postings often
  describe a concept in other words, so it counts even when its name is not in the text.
  A product counts only when the posting names it.
- `emerging`: the skill only became mainstream in 2022 or later (LLM, RAG, GitHub
  Copilot, Claude Code). The page shows how much of today's demand they make up.
- `ambiguous`: the name is also a normal word ("REST", "Go", "CAN"). The keyword search
  then only uses the safe spellings ("REST-API", "Golang", "CAN-Bus").

You can add skills at any time. Run `skillradar-transform` afterwards; old answers from
Claude are matched to the new list, nothing is sent again.

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

You don't need to run these commands by hand. The daily job (see below) sends the new open
postings, about 110 a day for about $0.75 a month, and waits for the answers. Set
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

## Gold tables

The numbers the webpage shows. They cover open tech postings that have an answer from
Claude, and are rebuilt with silver. Jobs that are not tech work (the search finds a few,
like sales or HR) are left out. `role` and `region` (German state) can also be `all`.

After each build the gold tables are also saved as Parquet files in `data/serve/`. The
page reads only these files, never the warehouse, so it can't block the daily build.

| Table | What it holds |
|---|---|
| `gold_skill_demand` | per role, region and skill: how many postings ask for it, how many require it, all postings in the group, and the share |
| `gold_attribute_shares` | per role and region: share of each seniority, home office option, and German and English level ("not asked" when a posting does not mention the language) |
| `gold_emerging_share` | per role and region: postings that ask for at least one skill from 2022 or later, and the share |
| `gold_postings` | one row per open tech posting: title, employer, place, role, seniority, home office, languages |
| `gold_posting_skills` | the skills each posting is counted for |
| `gold_posting_texts` | the cleaned text of each posting (contact details removed) |
| `gold_meta` | one row: date of the data, open postings, how many have an answer, how many are tech jobs, model and prompt version |
| `gold_scope` | which posting belongs to which role and region (used by the others) |

Two rules make the numbers honest:

- A product name that is not in the posting text is left out, because the model most
  likely made it up. Concepts (`general` skills) always count.
- A posting with places in two states counts in both states, and once in `all`.

Some groups are small (for example one role in one state), so a share can jump a lot.
Always show `total_postings` next to a share.

## Webpage

One page that answers the main question, which skills do German tech employers ask for,
from a few angles. Pick a role and a region at the top; everything below follows.

- **Headline numbers:** open postings, how many ask for fluent German, offer home office,
  and ask for new AI skills
- **What's in demand?** the top skills, split into required and nice to have
- **What does each role need?** a heatmap of roles and the most asked-for skills
- **Must-have or nice-to-have?** skills that are almost always required vs. often optional
- **How big is the AI wave?** the share of postings asking for skills that only became
  mainstream in 2022 or later (LLMs, RAG, AI coding tools), per role
- **Do you need German?** language level per role
- **What do the jobs look like?** home office and seniority
- **Where are the jobs?** a small map of the German states; click a state to filter
- **Open jobs** (sidebar): the postings for the chosen role and region, newest first.
  Click one to open it: key facts, its skills, and the full text with the important parts
  marked (required and nice-to-have skills, languages, home office), plus a link to the
  original posting. The address keeps the open job, so a link can point to it.

Every chart has a tooltip (mouse and keyboard) and a "Table" button with the same numbers.
Sections fade in, bars grow and the job view opens with a soft rise; all motion is turned
off when the system asks for reduced motion.
The page follows the Mac's light or dark mode and works on a phone. It runs on your Mac
only.

The data starts in October 2026, so the page can't compare with earlier years. The AI
section shows the closest honest thing: how much of today's demand is for skills that
barely existed in job postings before 2022. Real trends follow when more history exists.

First time, build the page (needs Node.js):

```sh
cd web && npm install && npm run build && cd ..
```

Then start it and open http://127.0.0.1:8000:

```sh
uv run skillradar-web
```

The page always shows the latest gold tables; reload it after the daily job ran. Build the
page again only when you change files in `web/`.

To work on the page with live reload, run `uv run skillradar-web` in one terminal and
`cd web && npm run dev` in another, then open http://localhost:3000.

Checks for the page: `npm run typecheck`, `npm run lint` and `npm run build` in `web/`.

The API is at `/api/dashboard?region=BAYERN` (everything the page shows for one region),
`/api/postings?role=data_engineer&region=BAYERN` (the job list),
`/api/postings/<refnr>` (one job with its marks),
`/api/overview` and `/api/skills?role=data_engineer&region=BAYERN` (docs at `/api/docs`). It only reads data, only listens on 127.0.0.1, and only accepts
known roles and regions.

## Public website (GitHub Pages)

A public copy of the page: https://omidrasouli22.github.io/skillradar/

GitHub Pages only serves files, so the public page reads JSON files instead of the API.
`skillradar-publish` writes them, adds the built page, and pushes everything to the
`gh-pages` branch as one replaced commit, so the repository does not grow.

What is public: the charts, the job list, and each job's profile (facts, key points,
skill profile) with a link to the original posting. **Full posting texts are not
published**: the employers own them, and a contact name can slip through the cleaning.
The full text with highlights stays in your local version.

Set up once:

```sh
cd web && npm install && npm run build:public && cd ..   # the public page, in web/out-public
uv run skillradar-publish --dry-run                       # build data/site without pushing
uv run skillradar-publish                                 # push it to the gh-pages branch
```

Then on GitHub: Settings → Pages → "Deploy from a branch" → `gh-pages`, folder `/ (root)`.

After that the daily job publishes by itself whenever the data changed (step 6 below).
Build the public page again only when you change files in `web/`. Turn publishing off
with `enabled: false` in `config/site.yaml`.

To look at the public version before pushing: after `--dry-run`, run
`mkdir -p data/preview && ln -sfn ../site data/preview/skillradar` and
`python3 -m http.server 8010 --directory data/preview`, then open
http://127.0.0.1:8010/skillradar/.

## Daily schedule (macOS)

```sh
uv run skillradar-schedule install             # every day at 08:00
uv run skillradar-schedule install --at 06:30  # another time
uv run skillradar-schedule run-now             # start it now
uv run skillradar-schedule uninstall
```

The job runs once a day. If the Mac is asleep at that time, it runs as soon as the Mac
wakes up. If the Mac is off, it runs at the next login. It runs `skillradar-daily`:

1. **Snapshot.** Skipped when today (UTC) already has a full `ok` or `partial` run, so a
   second start on the same day does nothing.
2. **Collect** Claude's batches that finished since the last run (free).
3. **Rebuild silver** when there are new postings or new answers.
4. **Send** new open postings to Claude, within the monthly limit. Postings that already
   have an answer or are in a running batch are never sent twice.
5. **Wait** for that batch (usually 5 to 15 minutes, at most 60), then rebuild silver again,
   so the day's answers are in the tables the same day. A slower batch is collected the
   next day.
6. **Publish** the public website when the data changed. If that fails (no network, the
   public page not built yet), you get a desktop alert; the rest of the job is not affected.

If something fails (the job API is down, or the dbt build breaks), it is tried again at
the next run, so the next day or at the next login. You can also start it by hand with
`run-now`. Problems with Claude (no key, limit reached, API down) are written to the log
and never stop the snapshot or silver. A rejected API key shows a desktop alert.

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
