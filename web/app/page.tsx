"use client";

import { useEffect, useState } from "react";
import { getOverview, getSkills, type Choice, type Overview, type SkillList } from "@/lib/api";
import { count, day, percent } from "@/lib/format";

const FIRST = 15;
const MORE = 30;
// Below this, one posting more or less moves a share by several points.
const SMALL_GROUP = 30;

type Result = { key: string; data?: SkillList; error?: string };

export default function Home() {
  const [overview, setOverview] = useState<Overview | null>(null);
  const [overviewError, setOverviewError] = useState<string | null>(null);
  const [role, setRole] = useState("all");
  const [region, setRegion] = useState("all");
  const [limit, setLimit] = useState(FIRST);
  const [result, setResult] = useState<Result | null>(null);

  const key = `${role}|${region}|${limit}`;

  useEffect(() => {
    const controller = new AbortController();
    getOverview(controller.signal)
      .then((data) => {
        // A shared link can choose the role and region; unknown values fall back to "all".
        const params = new URLSearchParams(window.location.search);
        setRole(pick(params.get("role"), data.roles));
        setRegion(pick(params.get("region"), data.regions));
        setOverview(data);
      })
      .catch((error: Error) => {
        if (error.name !== "AbortError") setOverviewError(error.message);
      });
    return () => controller.abort();
  }, []);

  useEffect(() => {
    if (!overview) return;
    const controller = new AbortController();
    getSkills(role, region, limit, controller.signal)
      .then((data) => setResult({ key, data }))
      .catch((error: Error) => {
        if (error.name !== "AbortError") setResult({ key, error: error.message });
      });
    // An older answer can't replace a newer one: it is aborted, and results carry their key.
    return () => controller.abort();
  }, [overview, role, region, limit, key]);

  function choose(nextRole: string, nextRegion: string) {
    setRole(nextRole);
    setRegion(nextRegion);
    setLimit(FIRST);
    const params = new URLSearchParams();
    if (nextRole !== "all") params.set("role", nextRole);
    if (nextRegion !== "all") params.set("region", nextRegion);
    const query = params.toString();
    window.history.replaceState(null, "", query ? `?${query}` : window.location.pathname);
  }

  const current = result?.key === key ? result : null;
  const shown = current?.data ?? result?.data;
  const loading = !current;

  return (
    <main className="page">
      <header className="top">
        <div className="brand">
          Skill<span>Radar</span>
        </div>
        {overview && <div>Data as of {day(overview.as_of)}</div>}
      </header>

      <section className="hero">
        <h1>Which skills do German tech employers ask for?</h1>
        <p>
          {overview ? (
            <>
              <strong>{count(overview.tech_postings)} open tech job postings</strong> from the
              Bundesagentur für Arbeit, each one read by an AI model that lists the skills it asks
              for.
            </>
          ) : (
            <>Open tech job postings from the Bundesagentur für Arbeit, read one by one by an AI model.</>
          )}
        </p>
      </section>

      {overviewError ? (
        <div className="card">
          <div className="state" role="alert">
            <strong>The data is not available.</strong>
            {overviewError}
          </div>
        </div>
      ) : (
        <>
          <div className="filters">
            <Select
              id="role"
              label="Role"
              value={role}
              choices={overview?.roles}
              onChange={(value) => choose(value, region)}
            />
            <Select
              id="region"
              label="Region"
              value={region}
              choices={overview?.regions}
              onChange={(value) => choose(role, value)}
            />
          </div>

          <section className="card" aria-labelledby="result-title" aria-busy={loading}>
            <div className="card-head">
              <div>
                <h2 id="result-title">
                  {label(overview?.roles, role)} · {label(overview?.regions, region)}
                </h2>
                <p>
                  {shown
                    ? `Share of ${count(shown.total_postings)} open postings that ask for each skill`
                    : "Loading…"}
                </p>
              </div>
              <div className="legend" aria-hidden="true">
                <span>
                  <i className="swatch-required" />
                  Required
                </span>
                <span>
                  <i className="swatch-optional" />
                  Nice to have
                </span>
              </div>
            </div>

            {current?.error ? (
              <div className="state" role="alert">
                <strong>Could not load the skills.</strong>
                {current.error}
              </div>
            ) : !shown ? (
              <Skeleton />
            ) : shown.total_postings === 0 ? (
              <div className="state">
                <strong>No open postings for this choice.</strong>
                Try another region or all regions.
              </div>
            ) : (
              <>
                {shown.total_postings < SMALL_GROUP && (
                  <p className="note">
                    Only {shown.total_postings} postings in this group, so each one moves a share by
                    several points. Read the numbers as a rough picture.
                  </p>
                )}
                <ol className={loading ? "skills loading" : "skills"}>
                  {shown.skills.map((skill, index) => (
                    <SkillRow key={skill.name} rank={index + 1} skill={skill} total={shown.total_postings} />
                  ))}
                </ol>
                {limit === FIRST && shown.skills.length === FIRST && (
                  <button className="more" type="button" onClick={() => setLimit(MORE)}>
                    Show top {MORE}
                  </button>
                )}
              </>
            )}
          </section>
        </>
      )}

      <footer className="method">
        <h3>How the numbers are made</h3>
        <p>
          Every day the open job postings are downloaded from the Bundesagentur für Arbeit. Contact
          details are removed, then {overview ? <code>{overview.model}</code> : "an AI model"} reads
          each posting and lists the technical skills it asks for, marked as required or nice to
          have. A share is the number of postings that ask for a skill, divided by all postings in
          the chosen role and region.
        </p>
        <p>
          Product names that a posting does not actually mention are left out, because the model
          most likely added them. Jobs that are not tech work are not counted. A posting with places
          in two regions counts in both.
        </p>
      </footer>
    </main>
  );
}

function Select(props: {
  id: string;
  label: string;
  value: string;
  choices?: Choice[];
  onChange: (value: string) => void;
}) {
  const { id, label: text, value, choices, onChange } = props;
  return (
    <div className="field">
      <label htmlFor={id}>{text}</label>
      <select
        id={id}
        value={value}
        disabled={!choices}
        onChange={(event) => onChange(event.target.value)}
      >
        {(choices ?? [{ id: "all", label: "Loading…", postings: 0 }]).map((choice) => (
          <option key={choice.id} value={choice.id}>
            {choices ? `${choice.label} (${count(choice.postings)})` : choice.label}
          </option>
        ))}
      </select>
    </div>
  );
}

function SkillRow({ rank, skill, total }: { rank: number; skill: SkillList["skills"][number]; total: number }) {
  const summary =
    `${skill.name}: asked for in ${count(skill.postings)} of ${count(total)} postings ` +
    `(${percent(skill.share)}), required in ${count(skill.required_postings)}.`;
  return (
    <li className="skill" title={summary}>
      <span className="rank">{rank}</span>
      <span className="name">{skill.name}</span>
      <span className="bar" aria-hidden="true">
        <span className="all" style={{ width: `${skill.share * 100}%` }} />
        <span className="required" style={{ width: `${skill.required_share * 100}%` }} />
      </span>
      <span className="value" aria-hidden="true">
        {percent(skill.share)}
      </span>
      <span className="sr-only">{summary}</span>
    </li>
  );
}

function Skeleton() {
  return (
    <div aria-hidden="true">
      {Array.from({ length: 8 }, (_, index) => (
        <div key={index} className="skeleton" />
      ))}
    </div>
  );
}

function pick(value: string | null, choices: Choice[]): string {
  return value && choices.some((choice) => choice.id === value) ? value : "all";
}

function label(choices: Choice[] | undefined, id: string): string {
  return choices?.find((choice) => choice.id === id)?.label ?? "…";
}
