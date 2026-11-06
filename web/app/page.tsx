"use client";

import { useEffect, useMemo, useState } from "react";
import { ChartCard, Swatch, type Table } from "@/components/ChartCard";
import { Heatmap, ScaleLegend } from "@/components/Heatmap";
import { JobDialog, type Origin } from "@/components/JobDialog";
import { JobList } from "@/components/JobList";
import { KpiRow, type Kpi } from "@/components/KpiRow";
import { RequiredLists } from "@/components/RequiredLists";
import { RoleBars } from "@/components/RoleBars";
import { SegmentedBar } from "@/components/SegmentedBar";
import { SkillBars } from "@/components/SkillBars";
import { StackedBars } from "@/components/StackedBars";
import { StateTiles } from "@/components/StateTiles";
import { TooltipProvider } from "@/components/Tooltip";
import { getDashboard, getOverview, type Choice, type Dashboard, type Overview, type Part } from "@/lib/api";
import { count, day, percent } from "@/lib/format";
import { GERMAN, REMOTE, SENIORITY } from "@/lib/labels";

const FIRST = 15;
const MORE = 30;
// Below this, one posting more or less moves a share by several points.
const SMALL_GROUP = 30;
// A skill must be this common in the group to be compared in "must-have or bonus".
const MIN_SHARE = 0.05;
const MIN_POSTINGS = 5;
// Reference numbers of the job search, as the API accepts them.
const REFNR = /^[A-Za-z0-9][A-Za-z0-9_-]{2,79}$/;

type Result = { region: string; data?: Dashboard; error?: string };

export default function Home() {
  const [overview, setOverview] = useState<Overview | null>(null);
  const [overviewError, setOverviewError] = useState<string | null>(null);
  const [region, setRegion] = useState("all");
  const [role, setRole] = useState("all");
  const [limit, setLimit] = useState(FIRST);
  const [result, setResult] = useState<Result | null>(null);
  const [job, setJob] = useState<string | null>(null);
  const [origin, setOrigin] = useState<Origin | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    getOverview(controller.signal)
      .then((data) => {
        // A shared link can choose the role and region; unknown values fall back to "all".
        const params = new URLSearchParams(window.location.search);
        setRole(pick(params.get("role"), data.roles));
        setRegion(pick(params.get("region"), data.regions));
        const shared = params.get("job");
        if (shared && REFNR.test(shared)) setJob(shared);
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
    getDashboard(region, controller.signal)
      .then((data) => setResult({ region, data }))
      .catch((error: Error) => {
        if (error.name !== "AbortError") setResult({ region, error: error.message });
      });
    // An older answer can't replace a newer one: it is aborted, and results carry their region.
    return () => controller.abort();
  }, [overview, region]);

  function choose(next: { role?: string; region?: string }) {
    const nextRole = next.role ?? role;
    const nextRegion = next.region ?? region;
    setRole(nextRole);
    setRegion(nextRegion);
    setLimit(FIRST);
    link(nextRole, nextRegion, job);
  }

  function openJob(refnr: string | null, from: Origin | null = null) {
    setJob(refnr);
    setOrigin(from);
    link(role, region, refnr);
  }

  const current = result?.region === region ? result : null;
  // While a new region loads, the previous charts stay, dimmed: no layout jump.
  const dash = current?.data ?? result?.data ?? null;
  const loading = !current;

  const roleLabel = label(overview?.roles, role);
  const regionLabel = label(overview?.regions, region);
  const where = region === "all" ? "in Germany" : `in ${regionLabel}`;
  const roleCounts = useMemo(() => Object.fromEntries((dash?.roles ?? []).map((r) => [r.id, r.postings])), [dash]);
  const total = roleCounts[role] ?? 0;

  return (
    <TooltipProvider>
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
                Bundesagentur für Arbeit, each one read by an AI model that lists the skills, the
                language level and the working model it asks for.
              </>
            ) : (
              "Open tech job postings from the Bundesagentur für Arbeit, read one by one by an AI model."
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
            <div className="filters" role="search" aria-label="Filter the page">
              <Select
                id="role"
                label="Role"
                value={role}
                choices={overview?.roles.map((r) => ({ ...r, postings: roleCounts[r.id] ?? 0 }))}
                onChange={(value) => choose({ role: value })}
              />
              <Select
                id="region"
                label="Region"
                value={region}
                choices={overview?.regions}
                onChange={(value) => choose({ region: value })}
              />
            </div>

            <div className="layout">
              <div className="main">
                {current?.error ? (
                  <div className="card">
                    <div className="state" role="alert">
                      <strong>Could not load the data.</strong>
                      {current.error}
                    </div>
                  </div>
                ) : !dash ? (
                  <div className="card">
                    <div className="state">Loading…</div>
                  </div>
                ) : (
                  <Sections
                    dash={dash}
                    role={role}
                    roleLabel={roleLabel}
                    region={region}
                    where={where}
                    total={total}
                    limit={limit}
                    loading={loading}
                    onMore={() => setLimit(MORE)}
                    choose={choose}
                  />
                )}
              </div>
              {overview && (
                <JobList
                  role={role}
                  region={region}
                  title={`${role === "all" ? "tech" : roleLabel} jobs ${where}`}
                  active={job}
                  onOpen={openJob}
                />
              )}
            </div>
            {job && <JobDialog key={job} refnr={job} origin={origin} onClose={() => openJob(null)} />}
          </>
        )}

        <footer className="method">
          <h3>How the numbers are made</h3>
          <p>
            Every day the open job postings are downloaded from the Bundesagentur für Arbeit.
            Contact details are removed, then {overview ? <code>{overview.model}</code> : "an AI model"}{" "}
            reads each posting and returns its role, seniority, home office, required languages
            and technical skills, each marked as required or nice to have. A share is the number
            of postings that ask for something, divided by all postings in the chosen role and
            region.
          </p>
          <p>
            Product names that a posting does not actually mention are left out, because the
            model most likely added them. Jobs that are not tech work are not counted. A posting
            with places in two states counts in both.
          </p>
        </footer>
      </main>
    </TooltipProvider>
  );
}

function Sections(props: {
  dash: Dashboard;
  role: string;
  roleLabel: string;
  region: string;
  where: string;
  total: number;
  limit: number;
  loading: boolean;
  onMore: () => void;
  choose: (next: { role?: string; region?: string }) => void;
}) {
  const { dash, role, roleLabel, region, where, total, limit, loading, onMore, choose } = props;
  const skills = (dash.skills[role] ?? []).slice(0, limit);
  const attributes = dash.attributes[role] ?? {};
  const emerging = dash.emerging[role] ?? { postings: 0, share: 0 };
  const german = attributes.german ?? [];
  const remote = attributes.remote ?? [];
  const whose = role === "all" ? "tech" : roleLabel;

  const kpis: Kpi[] = [
    { label: "Open postings", value: total, kind: "count", hint: `${whose} jobs ${where}` },
    {
      label: "Fluent German",
      value: shareOf(german, ["fluent", "native"]),
      kind: "share",
      hint: "ask for fluent or native German",
    },
    {
      label: "Home office",
      value: shareOf(remote, ["hybrid", "remote"]),
      kind: "share",
      hint: "offer hybrid or fully remote work",
    },
    { label: "New AI skills", value: emerging.share, kind: "share", hint: "ask for a skill from 2022 or later" },
  ];

  if (total === 0) {
    return (
      <>
        <KpiRow kpis={kpis} />
        <div className="card">
          <div className="state">
            <strong>
              No open {roleLabel} postings {where}.
            </strong>
            Choose another role or region.
          </div>
        </div>
      </>
    );
  }

  const allSkills = dash.skills[role] ?? [];
  const comparable = allSkills
    .filter((s) => s.share >= MIN_SHARE && s.postings >= MIN_POSTINGS)
    .map((s) => ({ skill: s, ratio: s.required_postings / s.postings }));
  const byRatio = [...comparable].sort((a, b) => b.ratio - a.ratio || b.skill.postings - a.skill.postings);
  const listSize = Math.min(5, Math.floor(byRatio.length / 2));
  const must = byRatio.slice(0, listSize).map((x) => x.skill);
  const bonus = byRatio.slice(-listSize).reverse().map((x) => x.skill);

  const roleRows = dash.roles.filter((r) => r.id !== "all");
  const emergingRows = roleRows
    .map((r) => ({
      id: r.id,
      label: r.label,
      total: r.postings,
      postings: dash.emerging[r.id]?.postings ?? 0,
      share: dash.emerging[r.id]?.share ?? 0,
    }))
    .sort((a, b) => b.share - a.share);
  const germanRows = dash.roles.map((r) => ({
    id: r.id,
    label: r.label,
    total: r.postings,
    parts: dash.attributes[r.id]?.german ?? [],
  }));
  const states = dash.states[role] ?? [];
  const topState = [...states].sort((a, b) => b.postings - a.postings)[0];
  const allGerman = dash.attributes.all?.german ?? [];

  return (
    <div className={loading ? "sections loading" : "sections"}>
      <KpiRow kpis={kpis} />

      <ChartCard
        id="demand"
        question="What's in demand?"
        answer={`The skills ${count(total)} ${whose} postings ${where} ask for most.`}
        legend={
          <>
            <Swatch tone="var(--required)" label="Required" />
            <Swatch tone="var(--nice)" label="Nice to have" />
          </>
        }
        table={skillTable(allSkills.slice(0, limit))}
      >
        {total < SMALL_GROUP && <SmallGroup total={total} />}
        <SkillBars skills={skills} total={total} />
        {limit === FIRST && allSkills.length > FIRST && (
          <button className="more" type="button" onClick={onMore}>
            Show top {MORE}
          </button>
        )}
      </ChartCard>

      <ChartCard
        id="roles"
        question="What does each role need?"
        answer="Share of each role's postings that ask for the most requested skills. Click a role to look at it."
        legend={<ScaleLegend />}
        table={{
          columns: ["Role", "Postings", ...dash.heatmap.skills],
          rows: dash.heatmap.rows.map((r) => [r.label, r.postings, ...r.shares.map(percent)]),
        }}
      >
        <Heatmap heatmap={dash.heatmap} selected={role} onSelect={(id) => choose({ role: id })} />
      </ChartCard>

      <ChartCard
        id="required"
        question="Must-have or nice-to-have?"
        answer={`When ${whose} postings ask for a skill, how often is it a must rather than a plus?`}
        table={{
          columns: ["Skill", "Asked for in", "Required in", "Required when asked"],
          rows: byRatio.map(({ skill, ratio }) => [skill.name, skill.postings, skill.required_postings, percent(ratio)]),
        }}
      >
        {listSize > 0 ? (
          <RequiredLists must={must} bonus={bonus} />
        ) : (
          <div className="state">Too few postings to compare skills here.</div>
        )}
      </ChartCard>

      <ChartCard
        id="ai"
        question="How big is the AI wave?"
        answer={
          <>
            {percent(dash.emerging.all?.share ?? 0)} of all tech postings {where} ask for at least one
            skill that only became mainstream in 2022 or later: LLMs, RAG and AI coding tools.
          </>
        }
        table={{
          columns: ["Role", "Postings", "Ask for a new AI skill", "Share"],
          rows: emergingRows.map((r) => [r.label, r.total, r.postings, percent(r.share)]),
        }}
      >
        <p className="aside">
          We started collecting postings in October 2026, so there is no data from five years ago.
          But these skills barely existed in job postings before 2022, so their share shows how much
          of today&apos;s demand is new.
        </p>
        <div className="split">
          <div>
            <h3 className="mini-title">Share of postings, by role</h3>
            <RoleBars rows={emergingRows} selected={role} onSelect={(id) => choose({ role: id })} />
          </div>
          <div>
            <h3 className="mini-title">The new skills, all roles</h3>
            <ul className="bars compact">
              {dash.emerging_skills.map((skill) => (
                <li key={skill.name} className="bar-row">
                  <span className="name">{skill.name}</span>
                  <span className="track" aria-hidden="true">
                    <span
                      className="fill one"
                      style={{ width: `${(skill.postings / (dash.emerging_skills[0]?.postings || 1)) * 100}%` }}
                    />
                  </span>
                  <span className="value">{count(skill.postings)}</span>
                </li>
              ))}
            </ul>
          </div>
        </div>
      </ChartCard>

      <ChartCard
        id="german"
        question="Do you need German?"
        answer={`${percent(shareOf(allGerman, ["fluent", "native"]))} of tech postings ${where} ask for fluent or native German, ${percent(shareOf(allGerman, ["not asked"]))} don't mention German at all.`}
        legend={GERMAN.map((level) => (
          <Swatch key={level.value} tone={level.tone} label={level.label} />
        ))}
        table={{
          columns: ["Role", "Postings", ...GERMAN.map((l) => l.label)],
          rows: germanRows.map((r) => [
            r.label,
            r.total,
            ...GERMAN.map((l) => percent(r.parts.find((p) => p.value === l.value)?.share ?? 0)),
          ]),
        }}
      >
        <StackedBars rows={germanRows} levels={GERMAN} selected={role} onSelect={(id) => choose({ role: id })} />
      </ChartCard>

      <ChartCard
        id="shape"
        question="What do the jobs look like?"
        answer={`Home office and seniority in ${count(total)} ${whose} postings ${where}.`}
        table={{
          columns: ["Question", "Answer", "Postings", "Share"],
          rows: [
            ...REMOTE.map((l) => partRow("Home office", l.label, remote, l.value)),
            ...SENIORITY.map((l) => partRow("Seniority", l.label, attributes.seniority ?? [], l.value)),
          ],
        }}
      >
        <SegmentedBar title="Home office" parts={remote} levels={REMOTE} total={total} />
        <SegmentedBar title="Seniority" parts={attributes.seniority ?? []} levels={SENIORITY} total={total} />
      </ChartCard>

      <ChartCard
        id="where"
        question="Where are the jobs?"
        answer={
          topState
            ? `Most ${whose} postings are in ${topState.label} (${count(topState.postings)}). Click a state to filter the page.`
            : "No postings with a German state."
        }
        legend={<ScaleLegendCount />}
        table={{
          columns: ["State", "Postings"],
          rows: [...states].sort((a, b) => b.postings - a.postings).map((s) => [s.label, s.postings]),
        }}
      >
        <div className="where">
          <StateTiles states={states} selected={region} onSelect={(id) => choose({ region: id })} />
          <div>
            <h3 className="mini-title">Postings by state</h3>
            <ul className="bars compact clickable">
              {[...states]
                .sort((a, b) => b.postings - a.postings)
                .map((state) => (
                  <li
                    key={state.id}
                    className={state.id === region ? "bar-row emphasis" : "bar-row"}
                    onClick={() => choose({ region: state.id === region ? "all" : state.id })}
                  >
                    <span className="name">{state.label}</span>
                    <span className="track" aria-hidden="true">
                      <span
                        className="fill one"
                        style={{ width: `${(state.postings / (topState?.postings || 1)) * 100}%` }}
                      />
                    </span>
                    <span className="value">{count(state.postings)}</span>
                  </li>
                ))}
            </ul>
          </div>
        </div>
      </ChartCard>
    </div>
  );
}

function SmallGroup({ total }: { total: number }) {
  return (
    <p className="note">
      Only {total} postings in this group, so each one moves a share by several points. Read the
      numbers as a rough picture.
    </p>
  );
}

function ScaleLegendCount() {
  return (
    <span className="scale">
      <span>fewer</span>
      {[1, 2, 3, 4, 5, 6, 7, 8].map((s) => (
        <i key={s} style={{ background: `var(--seq-${s})` }} />
      ))}
      <span>more postings</span>
    </span>
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
      <select id={id} value={value} disabled={!choices} onChange={(event) => onChange(event.target.value)}>
        {(choices ?? [{ id: "all", label: "Loading…", postings: 0 }]).map((choice) => (
          <option key={choice.id} value={choice.id}>
            {choices ? `${choice.label} (${count(choice.postings)})` : choice.label}
          </option>
        ))}
      </select>
    </div>
  );
}

function skillTable(skills: Dashboard["skills"][string]): Table {
  return {
    columns: ["Rank", "Skill", "Asked for in", "Share", "Required in"],
    rows: skills.map((s, i) => [i + 1, s.name, s.postings, percent(s.share), s.required_postings]),
  };
}

function partRow(question: string, answer: string, parts: Part[], value: string): (string | number)[] {
  const part = parts.find((p) => p.value === value);
  return [question, answer, part?.postings ?? 0, percent(part?.share ?? 0)];
}

function shareOf(parts: Part[], values: string[]): number {
  return parts.filter((p) => values.includes(p.value)).reduce((sum, p) => sum + p.share, 0);
}

// Keep the choices in the address, so a link opens the same view.
function link(role: string, region: string, job: string | null) {
  const params = new URLSearchParams();
  if (role !== "all") params.set("role", role);
  if (region !== "all") params.set("region", region);
  if (job) params.set("job", job);
  const query = params.toString();
  window.history.replaceState(null, "", query ? `?${query}` : window.location.pathname);
}

function pick(value: string | null, choices: Choice[]): string {
  return value && choices.some((choice) => choice.id === value) ? value : "all";
}

function label(choices: Choice[] | undefined, id: string): string {
  return choices?.find((choice) => choice.id === id)?.label ?? "…";
}
