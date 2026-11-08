# How SkillRadar works

The technical reference: every part, command and setting. For the short version, see the
[README](README.md).

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
| CI on GitHub Actions: lint, tests, dbt, site build, dependency audit | done |
| Weekly skill history (base for trends) | done |
| Skill trends over time | planned |
| Evaluation: sample, review page, report | done |
| Evaluation: verify the 150 drafted labels | in progress |
| Pipeline health page (local and public) | done |
| CV gap analysis (local page, example CVs) | done |
| Postgres export, hosting | planned |
| Forecasting | planned |

## Layout

```
.github/                CI workflow and weekly Dependabot updates
config/search.yaml      search terms, cities, API settings
config/skills.yaml      skill list: one name per skill, with category and other spellings
config/llm.yaml         model, prices, monthly spending limit, daily on/off
config/site.yaml        public website: on/off, git remote and branch
config/skill_families.yaml  which skills prove or partly replace others (CV analysis)
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
  health.py             the pipeline health page's data
  lock.py               stops two runs at the same time
  logs.py               logging setup for all commands
  notify.py             desktop alert when a run fails
  transform/            runs dbt (bronze → silver)
  clean/redact.py       removes emails, phones, links and contact names from texts
  skills/               skill list loader, name lookup, keyword search, report
  extract/              skill extraction with Claude: prompt, batches, spending limit,
                        daily step, quality numbers, silver table rows
  api/                  web API over the gold tables, and the command that starts the page
  evaluate/             labels, scores and the report for the extraction (eval/)
  cv/                   CV analysis: read a CV, compare it with the postings, example CVs
  publish/              the public website: data files and the push to GitHub Pages
  storage.py            atomic writes, private folders, JSON lines
web/                    the page (Next.js), built into static files in web/out
showcase/cv/            example CVs with expected results, and REPORT.md
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
uv run ruff format --check .
```

## Continuous integration

`.github/workflows/ci.yml` runs on every push to `main` and every pull request, in three
parallel jobs:

| Job | What it checks |
|---|---|
| Python and dbt | ruff lint and format, then pytest. The transform tests build the real dbt project on small test data, so a broken model fails here. |
| Website | eslint, typecheck, and `npm run build:public`, the same build that goes to GitHub Pages. |
| Dependency audit | `pip-audit` on the locked Python packages. `npm audit`: any known issue in what the site ships fails, for build tools only high or worse. |

No secrets are used: tests need no network and no API key. The workflow can only read the
repository, and every action is pinned to a commit. Dependabot opens grouped update pull
requests once a week for the actions, Python and npm packages, and CI checks them like any
other change.

CI only checks. The daily data run and the site upload still happen on the Mac (see
[Daily schedule](#daily-schedule-macos)).

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
| `silver_posting_regions` | posting and German state it lists (used for every region count) |
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

## Evaluation

How good is the extraction? `eval/labels.jsonl` holds the correct answer for a random
sample of 150 postings, written by the rules in [eval/GUIDE.md](eval/GUIDE.md). The
report compares three systems with these labels, on the same postings:

- the keyword search over `config/skills.yaml` (the baseline Claude has to beat),
- Claude's answers to the current prompt, every skill it named,
- the same answers as the site counts them (product names not in the text left out).

```sh
uv run skillradar-eval sample            # draw the sample (once; a fixed seed)
uv run skillradar-eval status            # labels per status
uv run skillradar-eval texts             # write the sample's texts for the review page
uv run skillradar-eval report            # score everything against verified labels
uv run skillradar-eval report --drafts   # also use unchecked drafts, marked as such
```

All commands are free: nothing is sent to Claude.

### How a label is made

Each label starts as a draft written by a model from the posting text alone, without
Claude's answer. A person then checks and corrects it on the review page and marks it
verified. Only verified labels count in the report, so the numbers say
"model-drafted, human-verified". The drafts were written by Claude Opus 5.5, a larger
model than the one being measured.

The review page runs locally: `uv run skillradar-web`, then open
`http://127.0.0.1:8000/label`. It shows the posting with the label's skills marked in the
text, a "not in text" hint for skills it can't find, and the choices for role,
seniority, home office and languages. ⌘/Ctrl + Enter verifies and opens the next
posting. The texts come from `data/eval/texts.jsonl` (local only, like all texts);
the labels file holds reference numbers and answers only, so it can live in the
repository. The page is left out of the public build.

### What the numbers mean

- Skills: micro precision and recall over all (posting, skill) pairs. The main number
  counts only skills in `config/skills.yaml`, where names match reliably. "All skills"
  also counts other skills by exact name, so "OIDC" and "OpenID Connect" differ: it is a
  lower bound.
- Required: for skills both sides found, how often required / nice to have agree.
- Role, seniority, home office: accuracy, with the most common mistakes.
- Languages: precision and recall of the language list, and accuracy of the level.
- Every number has a 95% bootstrap interval: the postings are drawn again with
  replacement 1,000 times, and the interval holds the middle 95% of the results. With
  150 postings an accuracy of 80% is roughly ±6 points.

The report goes to `data/eval/report.json`.

## CV analysis

A panel on the local start page, below the role and region filters (not on the public
site, which has no server). Add a CV, check and fix what was read, and compare it with
the open postings of the role and region chosen in the filters. Once a CV is loaded,
every card in the job list shows its match, and a posting's view shows how the CV
matches it: the score, its parts and the missing skills, like the "how you match" box on
job sites. Job sites like Jobscan compare a CV with one job ad at a time; this compares
it with every open posting, and ranks what to learn by the jobs it would open.

```sh
uv run skillradar-web                                      # the panel is on the start page
uv run skillradar-cv read my_cv.pdf --out profile.json     # or on the command line
uv run skillradar-cv match profile.json --role data_engineer --region BERLIN
uv run skillradar-cv showcase                              # check the example CVs
uv run skillradar-cv showcase --refresh                    # read them with Claude again (~$0.025)
uv run skillradar-cv showcase --stale                      # only those read with an older prompt
```

**Reading.** A PDF becomes text with pypdf (at most 5 MB and 10 pages; ligatures like
"ﬂ" are split, so "Airﬂow" is Airflow); the person can fix the text before it is read.
The call to Claude is streamed with a 60-second stall limit, because a plain call
sometimes hung for the SDK's full ten minutes. Emails, phone numbers, links and the name at the top are
replaced before the text goes to Claude (Haiku, about $0.002 a CV, counted in the monthly
limit). Claude returns a profile like a posting's answer: role, seniority, languages and
skills, each skill with where it shows (work, project, course, only listed). Like posting
answers, a product the CV does not name is dropped, and skills the keyword search finds
but Claude missed are added as "only listed". Two things are left to code, because a
language model gets them wrong: years of experience come from the jobs' dates (overlaps
once, working student jobs and apprenticeships left out), and language names are mapped
to the fixed list. A free "quick read" finds skill names by keyword only. Nothing about
the CV is saved or logged.

**Comparing** (`cv/match.py`). For each posting with at least three skills:
`skills × language × seniority`. Skills is the covered weight of the posting's skills
(required 1, nice to have 0.4). A CV skill counts 1.0 from work, 0.8 from a project, 0.7
from a course, 0.6 when only listed, and 0.8 times that when last used five or more years
ago. `config/skill_families.yaml` lists skills that prove a broader one (AWS proves Cloud
Computing: full credit) and skills that partly replace each other (AWS for Azure: at most
half). How much a substitute counts is learned from the postings: skills that appear with
the same other skills count more (`cv/similarity.py`). The same likeness names the known
skills a missing skill builds on. Language: 1 at the asked level, 0.7 one level short, 0.4
more. Seniority: 1 at the level, 0.8 one step up, 0.9 one step down, less further. Bands:
strong 70%+, good 50%+, partial 30%+.

**What to learn next.** For each missing skill asked in at least 3 postings (and 1%): if
the person learned it in a project (0.8), how many postings would become at least good?
Reaching fluent German or English is checked the same way. The list is ranked by that
number, not by how often a skill is asked.

**Example CVs** (`showcase/cv`). Fifteen fictional people, each built to test one thing:
a strong reference case, a senior with B1 German, a junior after a career change, German
CVs, a role switch, a team lead, an honest weak match, a CV with a prompt injection, a
working student, an ML engineer with LLM skills, a freelancer with overlapping projects,
an IT security analyst, a CV without any dates and a long CV with 16 years and about 50
skills. `tests/fixtures/cv_two_column.pdf` is a two-column CV printed by Chrome, to test
reading real PDFs.
Each `case.yaml` lists checks with the reason a person reading the CV would expect them.
Profile checks run in the tests on Claude's saved reading (`profile.json`); match checks
need today's postings and run in `skillradar-cv showcase`, which writes `REPORT.md`. On
the page, loading an example shows its checks next to the results.

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
| `gold_skill_weekly` | per week, role, region and skill: the same counts as `gold_skill_demand`, for the postings open that week |
| `gold_weeks` | per week: days with data, whether the week is over, open postings, how many have an answer (coverage) |

Two rules make the numbers honest:

- A product name that is not in the posting text is left out, because the model most
  likely made it up. Concepts (`general` skills) always count.
- A posting with places in two states counts in both states, and once in `all`.

Some groups are small (for example one role in one state), so a share can jump a lot.
Always show `total_postings` next to a share.

### Weekly history

`gold_skill_weekly` is the history for trends and, later, forecasts. A week runs Monday to
Sunday, and a posting counts in every week it was open on at least one day. A skill that a
group ever asked for has a row in every week the group had postings, with 0 when nobody
asked for it, so a series has no gaps. The table is rebuilt from bronze every time, so it
always uses the current skill list and the current answers.

Check `coverage` in `gold_weeks` before comparing weeks. Only postings with an answer to the
current prompt are counted, and a posting that closed before Claude read it never gets one.
The answers to prompt v4 were made on 6 November 2026, so earlier weeks only hold the
postings that were still open then: coverage is 71% and 74% for the two weeks before, and
87% for the week of 2 November. From then on the daily job sends each new posting while it
is open. A new prompt version lowers coverage the same way, until the open postings are
sent again.

## Pipeline health

`/health` on the local page and on the public site shows whether the pipeline works:

- **Freshness:** when the last run that saved data started. Fresh up to 30 hours, late up
  to 54, stale after that. The browser works this out again from the time, so a public
  copy that stopped updating shows as late or stale on its own.
- **Recent runs:** status, duration, open and new postings, failed searches, number of
  problems (never the error texts).
- **Last build:** dbt models and data tests by status, and the names of failed tests.
- **Claude:** model and prompt, spending this month against the limit, answers saved and
  failed, waiting batches, and the cost of each recent batch.
- **Answers per week:** coverage from `gold_weeks`.
- **Data layers:** bronze files and size, and rows per silver and gold table
  (`data/serve/table_counts.json`, written by each build).
- **Answer quality:** the evaluation's scores, shown only from verified labels.

`skillradar.health` builds it from files only (run logs, `dbt/target/run_results.json`,
the batch files, the gold Parquet files, `data/eval/report.json`), never the warehouse.
Each part is built on its own, so a broken file empties one part and never stops the
site from being published. Locally the page asks `/api/health`; the public site gets
`data/health.json` with every publish. It holds counts, dates and costs only: no file
paths, no error texts, no batch ids.

The public copy is updated when the site is published, which happens after a run that
changed the data. A failed run does not publish, so the page shows it by going late or
stale. Failed runs still send a desktop alert on this Mac (`notify.py`).

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

`uv run skillradar-figures` redraws the charts in the README (`assets/images/`) from the
latest data.

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
