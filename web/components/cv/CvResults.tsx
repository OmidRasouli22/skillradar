"use client";

import { useState } from "react";
import type { Origin } from "@/components/JobDialog";
import { BAND_LABEL, type Analysis, type Coverage, type Gap, type Match } from "@/lib/cv";
import { count, day, percent } from "@/lib/format";

const GAPS_FIRST = 8;
const DEMAND_FIRST = 15;
const MATCHES_FIRST = 10;

// Step 3: how the profile compares with the open postings of one role and region.
export function CvResults(props: {
  analysis: Analysis;
  loading: boolean;
  onRole: (role: string) => void;
  onOpen: (refnr: string, origin: Origin) => void;
}) {
  const { analysis, loading, onRole, onOpen } = props;
  const s = analysis.summary;
  const where = analysis.region === "all" ? "in Germany" : `in ${analysis.region_label}`;
  const what = analysis.role === "all" ? "tech jobs" : `${analysis.role_label} jobs`;
  const bestRole = analysis.roles[0];
  const topGap = analysis.gaps[0];

  if (s.scored === 0) {
    return (
      <div className="card">
        <div className="state">
          <strong>No postings to compare with</strong>
          There are no open {what} {where} that name at least three skills. Choose another role or region.
        </div>
      </div>
    );
  }

  return (
    <div className={loading ? "sections loading" : "sections"} aria-busy={loading}>
      <div className="kpis cv-kpis">
        <div className="kpi">
          <div className="kpi-label">Good or strong matches</div>
          <div className="kpi-value">{count(s.good_or_better)}</div>
          <div className="kpi-hint">
            of {count(s.scored)} {what} {where} ({percent(s.good_or_better / s.scored)})
          </div>
        </div>
        <div className="kpi">
          <div className="kpi-label">Typical match</div>
          <div className="kpi-value">{s.median === null ? "–" : percent(s.median)}</div>
          <div className="kpi-hint">median over these postings</div>
        </div>
        <div className="kpi">
          <div className="kpi-label">Best-fitting role</div>
          <div className="kpi-value cv-kpi-text">{bestRole ? bestRole.label : "–"}</div>
          <div className="kpi-hint">
            {bestRole ? `${percent(bestRole.share)} of its postings ${where} are a good match` : ""}
          </div>
        </div>
        <div className="kpi">
          <div className="kpi-label">Learn next</div>
          <div className="kpi-value cv-kpi-text">{topGap ? topGap.name : "–"}</div>
          <div className="kpi-hint">
            {topGap ? (topGap.gained ? `+${topGap.gained} postings become a good match` : "raises your match in many postings") : "no clear gap"}
          </div>
        </div>
      </div>

      <div className="cv-bandbar" aria-label="Postings by match">
        {(["strong", "good", "partial", "weak"] as const).map((band) =>
          s.bands[band] ? (
            <span key={band} className={band} style={{ flexGrow: s.bands[band] }} title={`${BAND_LABEL[band]}: ${s.bands[band]}`}>
              {s.bands[band] / s.scored >= 0.08 ? `${BAND_LABEL[band].split(" ")[0]} ${s.bands[band]}` : ""}
            </span>
          ) : null,
        )}
      </div>
      {s.postings > s.scored && (
        <p className="cv-muted cv-small">
          {count(s.postings - s.scored)} more postings name fewer than three skills; they are not scored because one or two
          skills say little about a fit.
        </p>
      )}

      <div className="cv-grid">
        <Gaps gaps={analysis.gaps} scored={s.scored} />
        <RoleFit analysis={analysis} onRole={onRole} />
      </div>
      <Demand analysis={analysis} />
      <Matches matches={analysis.matches} onOpen={onOpen} />
    </div>
  );
}

function Gaps({ gaps, scored }: { gaps: Gap[]; scored: number }) {
  const [all, setAll] = useState(false);
  const shown = all ? gaps : gaps.slice(0, GAPS_FIRST);
  return (
    <section className="card" aria-labelledby="cv-gaps-title">
      <div className="card-head">
        <div>
          <h2 id="cv-gaps-title">What to learn next</h2>
          <p>
            Ranked by how many postings would become at least a good match if you learned the skill in a solid project,
            not by how often it is asked.
          </p>
        </div>
      </div>
      {gaps.length === 0 ? (
        <p className="cv-muted">Nothing stands out: no missing skill is asked for often enough here.</p>
      ) : (
        <ol className="cv-gaps">
          {shown.map((gap, index) => (
            <li key={gap.name}>
              <span className="rank">{index + 1}</span>
              <div>
                <div className="cv-gap-head">
                  <strong>{gap.name}</strong>
                  <span className="cv-gap-gain">{gap.gained ? `+${gap.gained} good matches` : "small gains"}</span>
                </div>
                <div className="cv-gap-meta">
                  {gap.kind === "language" ? (
                    <>
                      asked in {count(gap.postings)} of {count(scored)} postings · you have{" "}
                      {gap.coverage.via ? gap.coverage.via : "none"}
                    </>
                  ) : (
                    <>
                      asked in {percent(gap.share)} of postings ({count(gap.required_postings)} require it)
                      {gap.coverage.kind === "substitute" && gap.coverage.via ? ` · partly covered by your ${gap.coverage.via}` : ""}
                    </>
                  )}
                </div>
                {gap.builds_on.length > 0 && (
                  <div className="cv-gap-builds">
                    Builds on your {gap.builds_on.join(", ")}
                  </div>
                )}
              </div>
            </li>
          ))}
        </ol>
      )}
      {gaps.length > GAPS_FIRST && (
        <button type="button" className="more" onClick={() => setAll(!all)}>
          {all ? "Show fewer" : `Show all ${gaps.length}`}
        </button>
      )}
    </section>
  );
}

function RoleFit({ analysis, onRole }: { analysis: Analysis; onRole: (role: string) => void }) {
  const roles = analysis.roles.filter((r) => r.scored >= 5).slice(0, 10);
  return (
    <section className="card" aria-labelledby="cv-roles-title">
      <div className="card-head">
        <div>
          <h2 id="cv-roles-title">Where you fit best</h2>
          <p>
            Share of each role&apos;s postings {analysis.region === "all" ? "in Germany" : `in ${analysis.region_label}`} that
            are at least a good match. Choose a role to compare with it.
          </p>
        </div>
      </div>
      {roles.length === 0 ? (
        <p className="cv-muted">Too few postings here to compare roles.</p>
      ) : (
        <ul className="bars clickable compact cv-roles">
          {roles.map((role) => (
            <li key={role.id}>
              <button
                type="button"
                className={`bar-row${role.id === analysis.role ? " emphasis" : ""}`}
                onClick={() => onRole(role.id)}
                aria-pressed={role.id === analysis.role}
                title={`${role.good_or_better} of ${role.scored} postings`}
              >
                <span className="name">{role.label}</span>
                <span className="track">
                  <span className="fill one" style={{ width: `${Math.max(role.share * 100, 1)}%` }} />
                </span>
                <span className="value">{percent(role.share)}</span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

function Demand({ analysis }: { analysis: Analysis }) {
  const [all, setAll] = useState(false);
  const rows = all ? analysis.demand : analysis.demand.slice(0, DEMAND_FIRST);
  const covered = analysis.demand.filter((d) => d.coverage.kind === "have" || d.coverage.kind === "proven").length;
  return (
    <section className="card" aria-labelledby="cv-demand-title">
      <div className="card-head">
        <div>
          <h2 id="cv-demand-title">The skills these postings ask for</h2>
          <p>
            You cover {covered} of the {analysis.demand.length} most asked skills. The bar is the share of postings that ask
            for the skill; its color shows whether your CV covers it.
          </p>
        </div>
      </div>
      <div className="legend">
        <span className="swatch">
          <i style={{ background: "var(--required)" }} />
          You have it
        </span>
        <span className="swatch">
          <i style={{ background: "var(--nice)" }} />
          Partly, through a similar skill
        </span>
        <span className="swatch">
          <i style={{ background: "var(--dim)" }} />
          Missing
        </span>
      </div>
      <ul className="bars cv-demand">
        {rows.map((row) => (
          <li key={row.skill} className="bar-row">
            <span className="name">{row.skill}</span>
            <span className="track">
              <span className={`fill ${tone(row.coverage)}`} style={{ width: `${Math.max(row.share * 100, 1)}%` }} />
            </span>
            <span className="value">{percent(row.share)}</span>
            <span className={`cv-status ${tone(row.coverage)}`}>{status(row.coverage, row.evidence)}</span>
          </li>
        ))}
      </ul>
      {analysis.demand.length > DEMAND_FIRST && (
        <button type="button" className="more" onClick={() => setAll(!all)}>
          {all ? "Show fewer" : `Show all ${analysis.demand.length}`}
        </button>
      )}
    </section>
  );
}

function Matches({ matches, onOpen }: { matches: Match[]; onOpen: (refnr: string, origin: Origin) => void }) {
  const [all, setAll] = useState(false);
  const shown = all ? matches : matches.slice(0, MATCHES_FIRST);
  return (
    <section className="card" aria-labelledby="cv-matches-title">
      <div className="card-head">
        <div>
          <h2 id="cv-matches-title">Your best matches</h2>
          <p>
            The open postings that fit your profile best. Each score is skills × language × seniority; open a posting to read
            it.
          </p>
        </div>
      </div>
      <ul className="cv-matches">
        {shown.map((m) => {
          const missing = m.skills.filter((k) => k.required && k.coverage.kind === "missing").map((k) => k.skill);
          const short = m.languages.filter((l) => m.parts.language < 1 && l.needed !== "not asked");
          return (
            <li key={m.refnr}>
              <button
                type="button"
                className="cv-match"
                onClick={(event) => {
                  const box = event.currentTarget.getBoundingClientRect();
                  onOpen(m.refnr, { x: box.left, y: box.top, width: box.width, height: box.height });
                }}
              >
                <div className={`cv-score ${m.band}`} aria-label={`${BAND_LABEL[m.band]}, ${percent(m.match)}`}>
                  <strong>{percent(m.match)}</strong>
                  <span>{m.band}</span>
                </div>
                <div className="cv-match-body">
                  <div className="job-title">{m.title}</div>
                  <div className="job-meta">
                    {[
                      m.employer,
                      m.city && m.regions > 1 ? `${m.city} and ${m.regions - 1} more region${m.regions > 2 ? "s" : ""}` : m.city,
                      m.published ? day(m.published, false) : null,
                    ]
                      .filter(Boolean)
                      .join(" · ")}
                  </div>
                  <div className="cv-parts">
                    <Part label="Skills" value={m.parts.skills} />
                    <Part label="Language" value={m.parts.language} />
                    <Part label="Seniority" value={m.parts.seniority} />
                  </div>
                  <div className="cv-match-skills">
                    {m.skills.map((k) => (
                      <span
                        key={k.skill}
                        className={`cv-skill ${tone(k.coverage)}${k.required ? "" : " nice"}`}
                        title={`${k.required ? "Required" : "Nice to have"}: ${status(k.coverage, null)}`}
                      >
                        {k.skill}
                      </span>
                    ))}
                  </div>
                  {(missing.length > 0 || short.length > 0) && (
                    <div className="cv-match-gaps">
                      {missing.length > 0 && <>Missing: {missing.join(", ")}. </>}
                      {short.map((l) => (
                        <span key={l.language}>
                          Asks {l.language} {l.needed === "unknown" ? "(no level)" : l.needed}, you have {l.have ?? "none"}.{" "}
                        </span>
                      ))}
                    </div>
                  )}
                </div>
              </button>
            </li>
          );
        })}
      </ul>
      {matches.length > MATCHES_FIRST && (
        <button type="button" className="more" onClick={() => setAll(!all)}>
          {all ? "Show fewer" : `Show all ${matches.length}`}
        </button>
      )}
    </section>
  );
}

function Part({ label, value }: { label: string; value: number }) {
  return (
    <span className="cv-part" title={`${label}: ${percent(value)}`}>
      <span>{label}</span>
      <span className="cv-part-track">
        <span style={{ width: `${value * 100}%` }} />
      </span>
    </span>
  );
}

function tone(coverage: Coverage): "have" | "partly" | "missing" {
  if (coverage.kind === "have" || coverage.kind === "proven") return "have";
  if (coverage.kind === "substitute") return "partly";
  return "missing";
}

function status(coverage: Coverage, evidence: string | null): string {
  switch (coverage.kind) {
    case "have":
      return evidence === "work" ? "used at work" : evidence ? `you have it (${evidenceText(evidence)})` : "you have it";
    case "proven":
      return `through ${coverage.via}`;
    case "substitute":
      return `partly, through ${coverage.via}`;
    default:
      return "missing";
  }
}

function evidenceText(evidence: string): string {
  return { project: "project", education: "course", listed: "listed" }[evidence] ?? evidence;
}
