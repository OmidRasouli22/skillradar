"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Parts, tone } from "@/components/cv/CvResults";
import { PostingText } from "@/components/PostingText";
import { getPosting, type Mark, type PostingDetail } from "@/lib/api";
import { BAND_LABEL, matchPosting, type CvProfile, type Match } from "@/lib/cv";
import { day, percent } from "@/lib/format";
import { GERMAN, label, REMOTE, SENIORITY } from "@/lib/labels";

// The closing animation takes about 300 ms; after this the dialog closes even if the
// browser never reports the animation's end.
const CLOSE_FALLBACK_MS = 420;

export type Origin = { x: number; y: number; width: number; height: number };
type Kind = Mark["kind"];

const KINDS: { kind: Kind; label: string }[] = [
  { kind: "required", label: "Required" },
  { kind: "nice", label: "Nice to have" },
  { kind: "language", label: "Language" },
  { kind: "home_office", label: "Home office" },
];

// One posting as a job profile: what it asks for, how that compares with other jobs in
// the same role, and the text with the important parts marked. It grows out of the card
// that was clicked and shrinks back into it.
export function JobDialog(props: {
  refnr: string;
  origin: Origin | null;
  onClose: () => void;
  // A loaded CV (local page only): the dialog then shows how it matches this posting.
  profile?: CvProfile | null;
}) {
  const { refnr, origin, onClose, profile } = props;
  const [fit, setFit] = useState<{ refnr: string; data: Match & { scored: boolean } } | null>(null);
  const dialog = useRef<HTMLDialogElement>(null);
  const body = useRef<HTMLDivElement>(null);
  const [state, setState] = useState<{ refnr: string; data?: PostingDetail; error?: string } | null>(null);
  const [closing, setClosing] = useState(false);
  const [hidden, setHidden] = useState<Set<Kind>>(new Set());
  const finished = useRef(false);
  const fallback = useRef<number | undefined>(undefined);

  const finish = useCallback(() => {
    if (finished.current) return;
    finished.current = true;
    window.clearTimeout(fallback.current);
    if (dialog.current?.open) dialog.current.close();
    onClose();
  }, [onClose]);

  useEffect(() => {
    const element = dialog.current;
    if (element && !element.open) element.showModal();
    return () => window.clearTimeout(fallback.current);
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    getPosting(refnr, controller.signal)
      .then((data) => setState({ refnr, data }))
      .catch((error: Error) => {
        if (error.name !== "AbortError") setState({ refnr, error: error.message });
      });
    return () => controller.abort();
  }, [refnr]);

  useEffect(() => {
    if (!profile) return;
    const controller = new AbortController();
    matchPosting(profile, refnr, controller.signal)
      .then((data) => setFit({ refnr, data }))
      .catch(() => undefined); // the posting still shows without the match
    return () => controller.abort();
  }, [refnr, profile]);

  function close() {
    if (closing) return;
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
      finish();
      return;
    }
    setClosing(true);
    fallback.current = window.setTimeout(finish, CLOSE_FALLBACK_MS);
  }

  function toggle(kind: Kind) {
    setHidden((old) => {
      const next = new Set(old);
      if (next.has(kind)) next.delete(kind);
      else next.add(kind);
      return next;
    });
  }

  // Scroll to a mark and let it pulse.
  function jump(index: number) {
    const mark = body.current?.querySelector<HTMLElement>(`mark[data-i="${index}"]`);
    if (!mark) return;
    mark.scrollIntoView({ behavior: "smooth", block: "center" });
    mark.classList.remove("pulse");
    void mark.offsetWidth; // restart the animation
    mark.classList.add("pulse");
  }

  const job = state?.refnr === refnr ? state.data : undefined;
  const match = profile && fit?.refnr === refnr ? fit.data : null;
  const coverage = new Map((match?.skills ?? []).map((k) => [k.skill.toLowerCase(), k.coverage]));
  const error = state?.refnr === refnr ? state.error : undefined;

  return (
    <dialog
      ref={dialog}
      className={closing ? "job-dialog closing" : "job-dialog"}
      style={fromCard(origin)}
      aria-labelledby="job-dialog-title"
      onCancel={(event) => {
        event.preventDefault();
        close();
      }}
      onClick={(event) => {
        if (event.target === dialog.current) close();
      }}
      onAnimationEnd={(event) => {
        if (closing && event.target === dialog.current) finish();
      }}
      // The browser may also close the dialog itself, e.g. on a second Esc.
      onClose={finish}
    >
      <div className="profile">
        <header className="profile-head">
          <div className="avatar" aria-hidden="true">
            {initials(job?.employer ?? job?.title ?? "")}
          </div>
          <div className="profile-title">
            <p className="profile-meta">{job ? job.role : "Loading…"}</p>
            <h2 id="job-dialog-title">{job?.title ?? (error ? "Not available" : " ")}</h2>
            {job && (
              <p className="profile-where">
                {[job.employer, job.city, job.published && `posted ${day(job.published)}`]
                  .filter(Boolean)
                  .join(" · ")}
              </p>
            )}
          </div>
          <div className="profile-actions">
            {job && (
              <a className="button" href={job.url} target="_blank" rel="noopener noreferrer">
                Original posting <span aria-hidden="true">↗</span>
              </a>
            )}
            <button type="button" className="close" onClick={close} aria-label="Close">
              <svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true">
                <path d="M6 6l12 12M18 6L6 18" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
              </svg>
            </button>
          </div>
          {job && (
            <ul className="glance">
              <Glance icon="level" name="Level" value={label(SENIORITY, job.seniority)} />
              <Glance icon="home" name="Home office" value={label(REMOTE, job.remote)} />
              <Glance icon="lang" name="German" value={label(GERMAN, job.german)} />
              <Glance icon="lang" name="English" value={label(GERMAN, job.english)} />
            </ul>
          )}
        </header>

        {error ? (
          <div className="state" role="alert">
            {error}
          </div>
        ) : !job ? (
          <div className="profile-body loading-body" aria-busy="true">
            {[0, 1, 2, 3, 4, 5, 6].map((i) => (
              <div key={i} className="skeleton-line" style={{ width: `${94 - i * 8}%` }} />
            ))}
          </div>
        ) : (
          <div className="profile-body" ref={body}>
            <aside className="profile-side">
              {match && <HowYouMatch match={match} />}
              <section className="insights">
                <h3>Key points</h3>
                <ul>
                  {keyPoints(job).map((point, i) => (
                    <li key={i} style={{ "--i": i } as React.CSSProperties}>
                      {point}
                    </li>
                  ))}
                </ul>
              </section>

              <section className="skill-profile">
                <h3>Skill profile</h3>
                <p className="hint">
                  How many {job.role} jobs ask for each skill.
                  {job.text && " Click one to find it in the text."}
                </p>
                <ul>
                  {job.skills.map((skill, i) => {
                    const first = job.marks.findIndex((m) => m.label === skill.name);
                    return (
                      <li key={skill.name} style={{ "--i": i } as React.CSSProperties}>
                        <button
                          type="button"
                          className={skill.required ? "skill-row required" : "skill-row nice"}
                          onClick={() => first >= 0 && jump(first)}
                          disabled={first < 0}
                          title={!job.text ? undefined : first < 0 ? "Described in other words in the text" : "Show in the text"}
                        >
                          <span className="skill-name">
                            {match && <CoverageMark kind={coverage.get(skill.name.toLowerCase())} />}
                            {skill.name}
                            {skill.emerging && <span className="badge">new</span>}
                          </span>
                          <span className="skill-kind">{skill.required ? "required" : "nice to have"}</span>
                          <span className="skill-bar" aria-hidden="true">
                            <span style={{ width: `${Math.max(skill.share_in_role * 100, 2)}%` }} />
                          </span>
                          <span className="skill-share">{percent(skill.share_in_role)}</span>
                        </button>
                      </li>
                    );
                  })}
                </ul>
              </section>
            </aside>

            {!job.text ? (
              <section className="profile-text elsewhere" aria-label="Job posting">
                <div className="elsewhere-card">
                  <svg viewBox="0 0 24 24" width="28" height="28" aria-hidden="true">
                    <path
                      d="M14 4h6v6M20 4l-9 9M18 14v5a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V7a1 1 0 0 1 1-1h5"
                      fill="none"
                      stroke="currentColor"
                      strokeWidth="1.8"
                      strokeLinecap="round"
                      strokeLinejoin="round"
                    />
                  </svg>
                  <h3>Read the full posting at the source</h3>
                  <p>
                    This public page shows what the AI found in the posting. The text itself belongs
                    to the employer and is published by the Bundesagentur für Arbeit.
                  </p>
                  <a className="button" href={job.url} target="_blank" rel="noopener noreferrer">
                    Open on arbeitsagentur.de <span aria-hidden="true">↗</span>
                  </a>
                </div>
              </section>
            ) : (
            <section className="profile-text" aria-label="Job posting">
              <div className="mark-filters" role="group" aria-label="Show marks">
                {KINDS.map((k) => {
                  const n = job.marks.filter((m) => m.kind === k.kind).length;
                  return (
                    <button
                      key={k.kind}
                      type="button"
                      className={`filter ${k.kind}`}
                      aria-pressed={!hidden.has(k.kind)}
                      onClick={() => toggle(k.kind)}
                      disabled={n === 0}
                    >
                      <i aria-hidden="true" />
                      {k.label}
                      <small>{n}</small>
                    </button>
                  );
                })}
              </div>
              {/* The minimap sits beside the scrolling text, so it always shows the whole posting. */}
              <div className="reading-wrap">
                <div className="reading">
                  <PostingText text={job.text} marks={job.marks} hidden={hidden} />
                </div>
                <MiniMap text={job.text} marks={job.marks} hidden={hidden} onJump={jump} />
              </div>
            </section>
            )}
          </div>
        )}
      </div>
    </dialog>
  );
}

// The dialog starts at the clicked card: CSS reads these as its first animation frame.
function fromCard(origin: Origin | null): React.CSSProperties {
  if (!origin || typeof window === "undefined") return {};
  const x = origin.x + origin.width / 2 - window.innerWidth / 2;
  const y = origin.y + origin.height / 2 - window.innerHeight / 2;
  const scale = Math.max(0.2, Math.min(0.6, origin.width / Math.min(1120, window.innerWidth)));
  return { "--from-x": `${x}px`, "--from-y": `${y}px`, "--from-s": scale } as React.CSSProperties;
}

function keyPoints(job: PostingDetail): React.ReactNode[] {
  const points: React.ReactNode[] = [];
  const required = job.skills.filter((s) => s.required);
  const nice = job.skills.filter((s) => !s.required);
  points.push(
    <>
      <strong>{required.length}</strong> required and <strong>{nice.length}</strong> nice-to-have skills
    </>,
  );
  const known = job.skills.filter((s) => s.share_in_role > 0);
  if (known.length > 1) {
    const rare = known.reduce((a, b) => (b.share_in_role < a.share_in_role ? b : a));
    const common = known.reduce((a, b) => (b.share_in_role > a.share_in_role ? b : a));
    points.push(
      <>
        Stands out with <strong>{rare.name}</strong>: only {percent(rare.share_in_role)} of {job.role} jobs ask for it
      </>,
    );
    points.push(
      <>
        Shares the basics: <strong>{common.name}</strong> is in {percent(common.share_in_role)} of {job.role} jobs
      </>,
    );
  }
  const unique = job.skills.filter((s) => s.share_in_role === 0);
  if (unique.length > 0) {
    points.push(
      <>
        Rare in this role: <strong>{unique.slice(0, 3).map((s) => s.name).join(", ")}</strong>
      </>,
    );
  }
  const emerging = job.skills.filter((s) => s.emerging);
  if (emerging.length > 0) {
    points.push(
      <>
        Asks for new AI skills: <strong>{emerging.map((s) => s.name).join(", ")}</strong>
      </>,
    );
  }
  points.push(
    job.german === "not asked" ? (
      <>German is not mentioned</>
    ) : (
      <>
        German: <strong>{label(GERMAN, job.german)}</strong>
      </>
    ),
  );
  return points;
}

function Glance({ icon, name, value }: { icon: "level" | "home" | "lang"; name: string; value: string }) {
  return (
    <li>
      <Icon name={icon} />
      <span>
        <small>{name}</small>
        {value}
      </span>
    </li>
  );
}

function Icon({ name }: { name: "level" | "home" | "lang" }) {
  const paths = {
    level: "M4 18h4v-5H4zM10 18h4V9h-4zM16 18h4V5h-4z",
    home: "M4 11l8-6 8 6v8a1 1 0 0 1-1 1h-4v-5h-6v5H5a1 1 0 0 1-1-1z",
    lang: "M4 6h9M8.5 4v2M6 6c.5 3 2.5 5.5 5 7M11 6c-.6 3.5-3 6.5-6 8M13 20l4-9 4 9M14.5 17h5",
  };
  return (
    <svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true" className="icon">
      <path d={paths[name]} fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

function initials(name: string): string {
  const words = name.replace(/\b(GmbH|AG|SE|KG|Co\.?|mbH|e\.V\.)\b/g, "").trim().split(/\s+/);
  return (words[0]?.[0] ?? "") + (words[1]?.[0] ?? "");
}

// A strip beside the text with a tick for each mark; click a tick to jump there.
function MiniMap(props: { text: string; marks: Mark[]; hidden: Set<Kind>; onJump: (i: number) => void }) {
  const { text, marks, hidden, onJump } = props;
  return (
    <div className="minimap" aria-hidden="true">
      {marks.map((mark, index) =>
        hidden.has(mark.kind) ? null : (
          <button
            key={index}
            type="button"
            tabIndex={-1}
            className={`tick ${mark.kind}`}
            style={{ top: `${(mark.start / Math.max(text.length, 1)) * 100}%` }}
            onClick={() => onJump(index)}
            title={mark.label}
          />
        ),
      )}
    </div>
  );
}

// The CV's match with this posting, like a "how you match" box on a job site.
function HowYouMatch({ match }: { match: Match & { scored: boolean } }) {
  const required = match.skills.filter((k) => k.required);
  const have = required.filter((k) => tone(k.coverage) === "have").length;
  const missing = required.filter((k) => tone(k.coverage) === "missing").map((k) => k.skill);
  return (
    <section className={`how-match ${match.band}`} aria-label="How your CV matches">
      <div className="how-match-head">
        <strong>{percent(match.match)}</strong>
        <span>
          {match.scored ? BAND_LABEL[match.band] : "Few skills named"}
          <small>
            {required.length ? `You have ${have} of ${required.length} required skills` : "No required skills named"}
          </small>
        </span>
      </div>
      <Parts parts={match.parts} />
      {missing.length > 0 && <p>Missing: {missing.join(", ")}</p>}
      {match.parts.language < 1 &&
        match.languages.map((l) => (
          <p key={l.language}>
            Asks {l.language} {l.needed === "unknown" ? "(no level given)" : l.needed}, you have {l.have ?? "none"}.
          </p>
        ))}
    </section>
  );
}

function CoverageMark({ kind }: { kind: Match["skills"][number]["coverage"] | undefined }) {
  const t = kind ? tone(kind) : "missing";
  const text = t === "have" ? "on your CV" : t === "partly" ? `partly, through ${kind?.via}` : "not on your CV";
  return (
    <span className={`cover-mark ${t}`} title={text} aria-label={text}>
      {t === "have" ? "✓" : t === "partly" ? "~" : "✗"}
    </span>
  );
}
