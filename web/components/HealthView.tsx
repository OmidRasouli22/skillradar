"use client";

import { useEffect, useState } from "react";
import { getHealth, PUBLIC_SITE, type Health } from "@/lib/api";
import { count, percent } from "@/lib/format";

type State = Health["freshness"]["state"];

const STATE_TEXT: Record<State, string> = {
  fresh: "Fresh",
  late: "Late",
  stale: "Stale",
};

const BASE = process.env.NEXT_PUBLIC_BASE_PATH ?? "";

// Is the pipeline healthy? Freshness is worked out again in the browser, so a public
// copy that stopped updating shows as late or stale on its own.
export function HealthView() {
  const [health, setHealth] = useState<Health | null>(null);
  const [now, setNow] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    getHealth(controller.signal)
      .then((data) => {
        setHealth(data);
        setNow(Date.now());
      })
      .catch((e: Error) => {
        if (e.name !== "AbortError") setError(e.message);
      });
    return () => controller.abort();
  }, []);

  const last = health?.freshness.last_success ?? null;
  const hours = last && now ? (now - Date.parse(last)) / 3_600_000 : null;
  const state: State = !health
    ? "stale"
    : hours === null
      ? "stale"
      : hours <= health.thresholds.fresh_hours
        ? "fresh"
        : hours <= health.thresholds.late_hours
          ? "late"
          : "stale";

  return (
    <main className="page health">
      <header className="top">
        <a className="brand" href={`${BASE}/`}>
          Skill<span>Radar</span>
        </a>
        {health && <div>Checked {moment(health.generated_at)}</div>}
      </header>

      <section className="hero">
        <h1>Pipeline health</h1>
        <p>
          Every morning a scheduled job downloads the open job postings, sends new ones to Claude, rebuilds and tests
          the tables, and publishes this site. This page shows whether that is working.
        </p>
      </section>

      {error ? (
        <div className="card state" role="alert">
          <strong>The health data is not available.</strong>
          {error}
        </div>
      ) : !health ? (
        <div className="card state">Loading…</div>
      ) : (
        <>
          <div className={`health-status ${state}`} role="status">
            <span className="dot" aria-hidden="true" />
            <div>
              <strong>{STATE_TEXT[state]}</strong>
              {last ? (
                <> · last successful run {ago(hours)}, {moment(last)}</>
              ) : (
                <> · no successful run yet</>
              )}
            </div>
          </div>

          <Kpis health={health} />
          <Runs runs={health.runs} />
          <div className="health-grid">
            <Tests tests={health.tests} />
            <Claude claude={health.claude} />
          </div>
        </>
      )}

      <footer className="method">
        <p>
          Fresh means the last successful run started less than {health?.thresholds.fresh_hours ?? 30} hours ago; late
          means less than {health?.thresholds.late_hours ?? 54} hours. {PUBLIC_SITE ? "This copy is updated when the site is published." : ""}
        </p>
      </footer>
    </main>
  );
}

function Kpis({ health }: { health: Health }) {
  const run = health.runs[0];
  const tests = health.tests?.tests ?? {};
  const testTotal = Object.values(tests).reduce((a, b) => a + b, 0);
  const claude = health.claude;
  return (
    <div className="kpis">
      <Tile label="Last run" value={run ? run.status : "none"} hint={run ? `${run.new_postings ?? 0} new postings` : ""} />
      <Tile
        label="Data tests passed"
        value={health.tests ? `${tests.pass ?? 0} / ${testTotal}` : "–"}
        hint={health.tests?.failures.length ? `${health.tests.failures.length} need a look` : "all passed"}
      />
      <Tile
        label="Postings with an answer"
        value={health.coverage?.share != null ? percent(health.coverage.share) : "–"}
        hint={health.coverage ? `${count(health.coverage.with_answer)} of ${count(health.coverage.open_postings)} open` : ""}
      />
      <Tile
        label="Claude this month"
        value={claude?.spent_usd != null ? usd(claude.spent_usd) : "–"}
        hint={claude ? `of ${usd(claude.budget_usd)} limit` : ""}
      />
    </div>
  );
}

function Tile({ label, value, hint }: { label: string; value: string; hint: string }) {
  return (
    <div className="kpi">
      <div className="kpi-label">{label}</div>
      <div className="kpi-value">{value}</div>
      <div className="kpi-hint">{hint}</div>
    </div>
  );
}

function Runs({ runs }: { runs: Health["runs"] }) {
  return (
    <section className="card">
      <div className="card-head">
        <div>
          <h2>Recent runs</h2>
          <p>One run a day. A partial run saved its data but missed some searches; those are tried again the next day.</p>
        </div>
      </div>
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Started</th>
              <th>Status</th>
              <th>Minutes</th>
              <th>Open postings</th>
              <th>New</th>
              <th>Failed searches</th>
              <th>Problems</th>
            </tr>
          </thead>
          <tbody>
            {runs.map((run) => (
              <tr key={run.run_id}>
                <td>{run.started_at ? moment(run.started_at) : run.run_id}</td>
                <td>
                  <span className={`run-status ${run.status}`}>{run.status}</span>
                </td>
                <td>{run.minutes ?? "–"}</td>
                <td>{run.unique_postings != null ? count(run.unique_postings) : "–"}</td>
                <td>{run.new_postings ?? "–"}</td>
                <td>{run.failed_queries ?? "–"}</td>
                <td>{run.errors}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function Tests({ tests }: { tests: Health["tests"] }) {
  return (
    <section className="card">
      <div className="card-head">
        <div>
          <h2>Last build</h2>
          <p>dbt builds every table and runs the data tests; a failed test stops the build.</p>
        </div>
      </div>
      {!tests ? (
        <p className="note">No build yet.</p>
      ) : (
        <dl className="facts">
          <dt>Finished</dt>
          <dd>{tests.finished_at ? moment(tests.finished_at) : "–"}</dd>
          <dt>Duration</dt>
          <dd>{tests.seconds} s</dd>
          <dt>Models</dt>
          <dd>{statusList(tests.models)}</dd>
          <dt>Data tests</dt>
          <dd>{statusList(tests.tests)}</dd>
          {tests.failures.length > 0 && (
            <>
              <dt>Need a look</dt>
              <dd>
                {tests.failures.map((f) => (
                  <code key={f.name}>
                    {f.name} ({f.status})
                  </code>
                ))}
              </dd>
            </>
          )}
        </dl>
      )}
    </section>
  );
}

function Claude({ claude }: { claude: Health["claude"] }) {
  return (
    <section className="card">
      <div className="card-head">
        <div>
          <h2>Claude</h2>
          <p>
            New postings go to Claude in batches at half price. Spending can never pass the monthly limit: a batch counts
            at its worst cost until its answers are in.
          </p>
        </div>
      </div>
      {!claude ? (
        <p className="note">No answers yet.</p>
      ) : (
        <>
          <dl className="facts">
            <dt>Model</dt>
            <dd>
              <code>{claude.model}</code>, prompt {claude.prompt_version}
            </dd>
            <dt>{claude.month}</dt>
            <dd>
              {claude.spent_usd != null ? usd(claude.spent_usd) : "–"} of {usd(claude.budget_usd)}
            </dd>
            <dt>Answers</dt>
            <dd>
              {count(claude.answers)} saved, {claude.failed_answers} failed
            </dd>
            <dt>Waiting</dt>
            <dd>
              {claude.pending_batches} batch{claude.pending_batches === 1 ? "" : "es"} ({count(claude.pending_postings)} postings)
            </dd>
          </dl>
          {claude.batches.length > 0 && (
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>Sent</th>
                    <th>Postings</th>
                    <th>Answers</th>
                    <th>Failed</th>
                    <th>Cost</th>
                  </tr>
                </thead>
                <tbody>
                  {claude.batches.map((b, i) => (
                    <tr key={`${b.created_at}-${i}`}>
                      <td>{b.created_at ? moment(b.created_at) : "–"}</td>
                      <td>{count(b.postings)}</td>
                      <td>{count(b.answers)}</td>
                      <td>{b.failed}</td>
                      <td>{b.cost_usd != null ? usd(b.cost_usd, 3) : "–"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </>
      )}
    </section>
  );
}

function statusList(counts: Record<string, number>): string {
  const parts = Object.entries(counts).map(([status, n]) => `${n} ${status}`);
  return parts.length ? parts.join(", ") : "none";
}

function usd(value: number, digits = 2): string {
  return `$${value.toFixed(digits)}`;
}

function ago(hours: number | null): string {
  if (hours === null) return "";
  if (hours < 1) return "less than an hour ago";
  if (hours < 48) return `${Math.round(hours)} hours ago`;
  return `${Math.round(hours / 24)} days ago`;
}

// Times in German time, where the pipeline runs.
function moment(iso: string): string {
  return new Date(iso).toLocaleString("en-GB", {
    day: "numeric",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
    timeZone: "Europe/Berlin",
  });
}
