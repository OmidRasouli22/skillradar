"use client";

import { useEffect, useRef, useState } from "react";
import { Demand, Gaps, Matches, RoleFit, Summary } from "@/components/cv/CvResults";
import { CvSource } from "@/components/cv/CvSource";
import { ProfileEditor } from "@/components/cv/ProfileEditor";
import { ShowcasePanel } from "@/components/cv/ShowcasePanel";
import type { Origin } from "@/components/JobDialog";
import {
  getShowcase,
  getShowcases,
  getStatus,
  LEVELS,
  readCv,
  SENIORITY,
  type CvProfile,
  type CvStatus,
  type Showcase,
  type ShowcaseItem,
} from "@/lib/cv";
import { count } from "@/lib/format";
import type { CvAnalysis } from "@/lib/useCv";

type Tab = "overview" | "learn" | "skills" | "matches" | "profile" | "checks";

// The CV on the start page (local only). Before a CV: an invitation and the input.
// After: the comparison with the page's role and region, in tabs.
export function CvPanel(props: {
  profile: CvProfile | null;
  onProfile: (profile: CvProfile | null) => void;
  analysis: CvAnalysis;
  whose: string;
  where: string;
  onRole: (role: string) => void;
  onOpenJob: (refnr: string, origin: Origin) => void;
}) {
  const { profile, onProfile, analysis, whose, where, onRole, onOpenJob } = props;
  const [status, setStatus] = useState<CvStatus | null>(null);
  const [showcases, setShowcases] = useState<ShowcaseItem[]>([]);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [text, setText] = useState("");
  const [reading, setReading] = useState<"claude" | "keywords" | null>(null);
  const [readError, setReadError] = useState<string | null>(null);
  const [notes, setNotes] = useState<string[]>([]);
  const [source, setSource] = useState("");
  const [showcase, setShowcase] = useState<Showcase | null>(null);
  const [edited, setEdited] = useState(false);
  const [tab, setTab] = useState<Tab>("overview");
  const panel = useRef<HTMLElement>(null);

  useEffect(() => {
    Promise.all([getStatus(), getShowcases()])
      .then(([s, list]) => {
        setStatus(s);
        setShowcases(list);
      })
      .catch((error: Error) => setLoadError(error.message));
  }, []);

  function start(next: CvProfile, nextNotes: string[], label: string, example: Showcase | null) {
    onProfile(next);
    setNotes(nextNotes);
    setSource(label);
    setShowcase(example);
    setEdited(false);
    setTab("overview");
    window.requestAnimationFrame(() => panel.current?.scrollIntoView({ behavior: "smooth", block: "start" }));
  }

  async function read(mode: "claude" | "keywords") {
    setReading(mode);
    setReadError(null);
    try {
      const answer = await readCv(text, mode);
      const label = mode === "claude" ? `read by ${status?.model ?? "Claude"} for $${answer.cost_usd.toFixed(4)}` : "quick keyword read";
      start(answer.profile, answer.notes, label, null);
      if (mode === "claude") getStatus().then(setStatus).catch(() => undefined);
    } catch (error) {
      setReadError((error as Error).message);
    } finally {
      setReading(null);
    }
  }

  async function loadExample(id: string) {
    setReadError(null);
    try {
      const example = await getShowcase(id);
      setText(example.text);
      if (!example.profile) {
        setReadError("This example has no saved reading yet: run skillradar-cv showcase --refresh.");
        return;
      }
      start(example.profile, example.notes, "the example's saved reading", example);
      onRole(example.target.role);
    } catch (error) {
      setReadError((error as Error).message);
    }
  }

  function reset() {
    onProfile(null);
    setShowcase(null);
    setNotes([]);
    setText("");
    setReadError(null);
  }

  if (loadError) return null; // no local API (e.g. a static copy): the page works without the CV part

  if (!profile) {
    return (
      <section ref={panel} id="cv" className="cv-panel cv-intro" aria-labelledby="cv-title">
        <div className="cv-intro-text">
          <span className="cv-eyebrow">Your CV</span>
          <h2 id="cv-title">How well do you fit these jobs?</h2>
          <p>
            Add your CV and see, for {whose} jobs {where}: how many fit you, which role suits you best, and the one skill that
            would open the most doors.
          </p>
          <ul className="cv-promises">
            <li>
              <b>Compared with every posting</b>, not one job ad at a time
            </li>
            <li>
              <b>Ranks what to learn</b> by the jobs it opens, German included
            </li>
            <li>
              <b>Private:</b> runs on this computer, contact details removed, nothing saved
            </li>
          </ul>
        </div>
        <CvSource
          status={status}
          text={text}
          onText={(value) => setText(value)}
          showcases={showcases}
          example={showcase?.id ?? null}
          onExample={loadExample}
          onRead={read}
          reading={reading}
          error={readError}
        />
      </section>
    );
  }

  const data = analysis.data;
  const german = profile.languages.find((l) => l.language === "German")?.level;
  const tabs: [Tab, string, number | null][] = [
    ["overview", "Overview", null],
    ["learn", "Learn next", data?.gaps.length ?? null],
    ["skills", "Skills", data ? data.demand.length : null],
    ["matches", "Best matches", data ? data.summary.good_or_better : null],
    ["profile", "Your profile", profile.skills.length],
    ...(showcase ? ([["checks", "Example checks", null]] as [Tab, string, null][]) : []),
  ];
  const good = data && data.summary.scored ? data.summary.good_or_better / data.summary.scored : 0;

  return (
    <section ref={panel} id="cv" className="cv-panel cv-ready" aria-labelledby="cv-title" aria-busy={analysis.loading}>
      <div className="cv-head">
        <div className="cv-ring" style={{ "--p": good } as React.CSSProperties} aria-hidden="true">
          <span>{data ? `${Math.round(good * 100)}%` : "…"}</span>
        </div>
        <div className="cv-who">
          <span className="cv-eyebrow">{showcase ? `Example · ${showcase.person}` : "Your CV"}</span>
          <h2 id="cv-title">{profile.headline || "Your profile"}</h2>
          <div className="cv-chips">
            <span>{SENIORITY.find((s) => s.value === profile.seniority)?.label ?? profile.seniority}</span>
            {profile.years_experience !== null && <span>{profile.years_experience} yrs in IT</span>}
            <span>German: {german ? LEVELS.find((l) => l.value === german)?.label.split(" ")[0] : "none"}</span>
            <span>{profile.skills.length} skills</span>
          </div>
          <p className="cv-muted">
            {data
              ? `${count(data.summary.good_or_better)} of ${count(data.summary.scored)} ${whose} jobs ${where} are at least a good match. Change the role or region above to compare with other jobs.`
              : "Comparing with the postings…"}
          </p>
        </div>
        <button type="button" className="toggle" onClick={reset}>
          New CV
        </button>
      </div>

      <div className="cv-tabbar" role="tablist" aria-label="CV analysis">
        {tabs.map(([id, label, n]) => (
          <button
            key={id}
            type="button"
            role="tab"
            aria-selected={tab === id}
            className={tab === id ? "active" : ""}
            onClick={() => setTab(id)}
          >
            {label}
            {n !== null && <small>{n}</small>}
          </button>
        ))}
      </div>

      <div className={analysis.loading && data ? "cv-tab-body loading" : "cv-tab-body"} key={tab} role="tabpanel">
        {analysis.error ? (
          <div className="state" role="alert">
            <strong>The comparison failed.</strong>
            {analysis.error}
          </div>
        ) : tab === "profile" ? (
          status && (
            <ProfileEditor
              profile={profile}
              onChange={(next) => {
                onProfile(next);
                setEdited(true);
              }}
              notes={notes}
              skillNames={status.skills}
              roles={status.roles.filter((r) => r.id !== "all")}
              from={source}
            />
          )
        ) : tab === "checks" && showcase ? (
          <ShowcasePanel showcase={showcase} edited={edited} />
        ) : !data ? (
          <div className="state">Comparing with the postings…</div>
        ) : data.summary.scored === 0 ? (
          <div className="state">
            <strong>No postings to compare with</strong>
            There are no open {whose} jobs {where} that name at least three skills. Choose another role or region above.
          </div>
        ) : tab === "overview" ? (
          <>
            <Summary analysis={data} whose={whose} where={where} />
            <div className="cv-columns">
              <div>
                <h3 className="mini-title">Where you fit best</h3>
                <RoleFit analysis={data} onRole={onRole} />
              </div>
              <div>
                <h3 className="mini-title">Learn next</h3>
                <Gaps gaps={data.gaps} scored={data.summary.scored} limit={4} />
                {data.gaps.length > 4 && (
                  <button type="button" className="cv-link" onClick={() => setTab("learn")}>
                    All {data.gaps.length} suggestions →
                  </button>
                )}
              </div>
            </div>
          </>
        ) : tab === "learn" ? (
          <>
            <p className="cv-muted">
              Ranked by how many postings would become at least a good match if you learned the skill in a solid project,
              not by how often it is asked.
            </p>
            <Gaps gaps={data.gaps} scored={data.summary.scored} />
          </>
        ) : tab === "skills" ? (
          <Demand analysis={data} />
        ) : (
          <Matches matches={data.matches} onOpen={onOpenJob} />
        )}
      </div>
    </section>
  );
}
