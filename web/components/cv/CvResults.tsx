"use client";

import { useState } from "react";
import type { Origin } from "@/components/JobDialog";
import { useCountUp } from "@/hooks/motion";
import { BAND_LABEL, type Analysis, type Coverage, type Gap, type Match } from "@/lib/cv";
import { count, day, percent } from "@/lib/format";

const MATCHES_FIRST = 8;

// The parts of the CV comparison, shown in the tabs of the CV panel.

export function Summary({ analysis, whose, where }: { analysis: Analysis; whose: string; where: string }) {
  const s = analysis.summary;
  const bestRole = analysis.roles[0];
  const topGap = analysis.gaps[0];
  return (
    <>
      <div className="kpis cv-kpis">
        <Tile label="Good or strong matches" value={s.good_or_better} hint={`of ${count(s.scored)} ${whose} jobs ${where}`} />
        <Tile label="Typical match" value={s.median ?? 0} share hint="median over these postings" />
        <div className="kpi" style={{ "--i": 2 } as React.CSSProperties}>
          <div className="kpi-label">Best-fitting role</div>
          <div className="kpi-value cv-kpi-text">{bestRole ? bestRole.label : "–"}</div>
          <div className="kpi-hint">{bestRole ? `${percent(bestRole.share)} of its postings are a good match` : ""}</div>
        </div>
        <div className="kpi" style={{ "--i": 3 } as React.CSSProperties}>
          <div className="kpi-label">Learn next</div>
          <div className="kpi-value cv-kpi-text">{topGap ? topGap.name : "–"}</div>
          <div className="kpi-hint">
            {topGap ? (topGap.gained ? `+${topGap.gained} postings become a good match` : "lifts many matches a little") : "no clear gap"}
          </div>
        </div>
      </div>
      <div className="cv-bandbar" role="img" aria-label={bandText(analysis)}>
        {(["strong", "good", "partial", "weak"] as const).map((b) =>
          s.bands[b] ? (
            <span key={b} className={b} style={{ flexGrow: s.bands[b] }} title={`${BAND_LABEL[b]}: ${s.bands[b]}`}>
              {s.bands[b] / s.scored >= 0.09 ? `${BAND_LABEL[b].split(" ")[0]} ${s.bands[b]}` : ""}
            </span>
          ) : null,
        )}
      </div>
      {s.postings > s.scored && (
        <p className="cv-small">
          {count(s.postings - s.scored)} postings name fewer than three skills and are not scored: one or two skills say
          little about a fit.
        </p>
      )}
    </>
  );
}

function Tile({ label, value, hint, share = false }: { label: string; value: number; hint: string; share?: boolean }) {
  const shown = useCountUp(value);
  return (
    <div className="kpi">
      <div className="kpi-label">{label}</div>
      <div className="kpi-value">{share ? percent(shown) : count(Math.round(shown))}</div>
      <div className="kpi-hint">{hint}</div>
    </div>
  );
}

function bandText(analysis: Analysis): string {
  const b = analysis.summary.bands;
  return `Strong ${b.strong}, good ${b.good}, partial ${b.partial}, weak ${b.weak}`;
}

export function Gaps({ gaps, scored, limit }: { gaps: Gap[]; scored: number; limit?: number }) {
  const shown = limit ? gaps.slice(0, limit) : gaps;
  if (gaps.length === 0) {
    return <p className="cv-muted">Nothing stands out: no missing skill is asked for often enough here.</p>;
  }
  const most = Math.max(...gaps.map((g) => g.gained), 1);
  return (
    <ol className="cv-gaps">
      {shown.map((gap, index) => (
        <li key={gap.name} style={{ "--i": index } as React.CSSProperties}>
          <span className="rank">{index + 1}</span>
          <div>
            <div className="cv-gap-head">
              <strong>{gap.name}</strong>
              <span className="cv-gap-gain">{gap.gained ? `+${gap.gained}` : "small"}</span>
            </div>
            <span className="cv-gap-track" aria-hidden="true">
              <span style={{ width: `${(gap.gained / most) * 100}%` }} />
            </span>
            <div className="cv-gap-meta">
              {gap.kind === "language" ? (
                <>
                  asked in {count(gap.postings)} of {count(scored)} postings · you have {gap.coverage.via ?? "none"}
                </>
              ) : (
                <>
                  asked in {percent(gap.share)} of postings ({count(gap.required_postings)} require it)
                  {gap.coverage.kind === "substitute" && gap.coverage.via ? ` · partly covered by your ${gap.coverage.via}` : ""}
                </>
              )}
            </div>
            {gap.builds_on.length > 0 && <div className="cv-gap-builds">Builds on your {gap.builds_on.join(", ")}</div>}
          </div>
        </li>
      ))}
    </ol>
  );
}

export function RoleFit({ analysis, onRole }: { analysis: Analysis; onRole: (role: string) => void }) {
  const roles = analysis.roles.filter((r) => r.scored >= 5).slice(0, 8);
  if (roles.length === 0) return <p className="cv-muted">Too few postings here to compare roles.</p>;
  return (
    <ul className="bars clickable compact cv-roles">
      {roles.map((role) => (
        <li key={role.id}>
          <button
            type="button"
            className={`bar-row${role.id === analysis.role ? " emphasis" : ""}`}
            onClick={() => onRole(role.id)}
            aria-pressed={role.id === analysis.role}
            title={`${role.good_or_better} of ${role.scored} postings are a good match. Show this role.`}
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
  );
}

export function Demand({ analysis }: { analysis: Analysis }) {
  const covered = analysis.demand.filter((d) => d.coverage.kind === "have" || d.coverage.kind === "proven").length;
  return (
    <>
      <p className="cv-muted">
        You cover <strong>{covered}</strong> of the {analysis.demand.length} skills these postings ask for most. The bar is
        how many postings ask for the skill; its color, whether your CV covers it.
      </p>
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
        {analysis.demand.map((row) => (
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
    </>
  );
}

export function Matches({ matches, onOpen }: { matches: Match[]; onOpen: (refnr: string, origin: Origin) => void }) {
  const [all, setAll] = useState(false);
  const shown = all ? matches : matches.slice(0, MATCHES_FIRST);
  return (
    <>
      <ul className="cv-matches">
        {shown.map((m, index) => {
          const missing = m.skills.filter((k) => k.required && k.coverage.kind === "missing").map((k) => k.skill);
          const short = m.parts.language < 1 ? m.languages : [];
          return (
            <li key={m.refnr} style={{ "--i": Math.min(index, 10) } as React.CSSProperties}>
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
                  <Parts parts={m.parts} />
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
    </>
  );
}

export function Parts({ parts }: { parts: Match["parts"] }) {
  return (
    <div className="cv-parts">
      {(
        [
          ["Skills", parts.skills],
          ["Language", parts.language],
          ["Seniority", parts.seniority],
        ] as [string, number][]
      ).map(([label, value]) => (
        <span key={label} className="cv-part" title={`${label}: ${percent(value)}`}>
          <span>{label}</span>
          <span className="cv-part-track">
            <span style={{ width: `${value * 100}%` }} />
          </span>
        </span>
      ))}
    </div>
  );
}

export function tone(coverage: Coverage): "have" | "partly" | "missing" {
  if (coverage.kind === "have" || coverage.kind === "proven") return "have";
  if (coverage.kind === "substitute") return "partly";
  return "missing";
}

export function status(coverage: Coverage, evidence: string | null): string {
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
