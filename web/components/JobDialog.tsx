"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { getPosting, type Mark, type PostingDetail } from "@/lib/api";
import { day } from "@/lib/format";
import { GERMAN, label, REMOTE, SENIORITY } from "@/lib/labels";

// The closing animation takes 220 ms; after this the dialog closes even if the browser
// never reports the animation's end.
const CLOSE_FALLBACK_MS = 320;

const KINDS: { kind: Mark["kind"]; label: string }[] = [
  { kind: "required", label: "Required skill" },
  { kind: "nice", label: "Nice-to-have skill" },
  { kind: "language", label: "Language" },
  { kind: "home_office", label: "Home office" },
];

// One posting in a dialog: key facts, skills, and the text with the important parts
// marked. Opens with a rise-and-fade, closes the same way; Esc and the backdrop close it.
export function JobDialog({ refnr, onClose }: { refnr: string; onClose: () => void }) {
  const dialog = useRef<HTMLDialogElement>(null);
  const [state, setState] = useState<{ refnr: string; data?: PostingDetail; error?: string } | null>(null);
  const [closing, setClosing] = useState(false);
  const finished = useRef(false);
  const fallback = useRef<number | undefined>(undefined);

  // Closes for real, once, however the close started.
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

  function close() {
    if (closing) return;
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
      finish();
      return;
    }
    setClosing(true);
    fallback.current = window.setTimeout(finish, CLOSE_FALLBACK_MS);
  }

  const current = state?.refnr === refnr ? state : null;
  const job = current?.data;

  return (
    <dialog
      ref={dialog}
      className={closing ? "job-dialog closing" : "job-dialog"}
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
      <div className="dialog-panel">
        <header className="dialog-head">
          <div>
            <p className="dialog-meta">
              {job ? [job.role, job.city, job.published && day(job.published)].filter(Boolean).join(" · ") : "Loading…"}
            </p>
            <h2 id="job-dialog-title">{job?.title ?? (current?.error ? "Not available" : " ")}</h2>
            {job?.employer && <p className="dialog-employer">{job.employer}</p>}
          </div>
          <div className="dialog-actions">
            {job && (
              <a className="button" href={job.url} target="_blank" rel="noopener noreferrer">
                Original posting ↗
              </a>
            )}
            <button type="button" className="close" onClick={close} aria-label="Close">
              ×
            </button>
          </div>
        </header>

        {current?.error ? (
          <div className="state" role="alert">
            {current.error}
          </div>
        ) : !job ? (
          <div className="dialog-body" aria-busy="true">
            {[0, 1, 2, 3, 4, 5].map((i) => (
              <div key={i} className="skeleton-line" style={{ width: `${92 - i * 9}%` }} />
            ))}
          </div>
        ) : (
          <div className="dialog-body">
            <dl className="facts" style={{ "--i": 0 } as React.CSSProperties}>
              <Fact name="Seniority" value={label(SENIORITY, job.seniority)} />
              <Fact name="Home office" value={label(REMOTE, job.remote)} />
              <Fact name="German" value={label(GERMAN, job.german)} />
              <Fact name="English" value={label(GERMAN, job.english)} />
            </dl>

            <div className="chips-block" style={{ "--i": 1 } as React.CSSProperties}>
              <Chips title="Required" skills={job.skills.filter((s) => s.required)} kind="required" />
              <Chips title="Nice to have" skills={job.skills.filter((s) => !s.required)} kind="nice" />
            </div>

            <div className="mark-legend" style={{ "--i": 2 } as React.CSSProperties}>
              {KINDS.map((k) => (
                <span key={k.kind} className={`legend-mark ${k.kind}`}>
                  {k.label}
                </span>
              ))}
            </div>

            <article className="posting-text" style={{ "--i": 3 } as React.CSSProperties}>
              <MarkedText text={job.text} marks={job.marks} />
            </article>
          </div>
        )}
      </div>
    </dialog>
  );
}

function Fact({ name, value }: { name: string; value: string }) {
  return (
    <div>
      <dt>{name}</dt>
      <dd>{value}</dd>
    </div>
  );
}

function Chips(props: {
  title: string;
  skills: PostingDetail["skills"];
  kind: "required" | "nice";
}) {
  const { title, skills, kind } = props;
  if (skills.length === 0) return null;
  return (
    <div>
      <h3 className="mini-title">{title}</h3>
      <ul className="chips">
        {skills.map((skill, index) => (
          <li key={skill.name} className={`chip ${kind}`} style={{ "--i": index } as React.CSSProperties}>
            {skill.name}
            {skill.emerging && <span className="badge">new</span>}
          </li>
        ))}
      </ul>
    </div>
  );
}

// The text as plain strings and <mark> elements; the text itself is never HTML.
function MarkedText({ text, marks }: { text: string; marks: Mark[] }) {
  const parts: React.ReactNode[] = [];
  let at = 0;
  marks.forEach((mark, index) => {
    if (mark.start > at) parts.push(text.slice(at, mark.start));
    parts.push(
      <mark
        key={index}
        className={mark.kind}
        title={KINDS.find((k) => k.kind === mark.kind)?.label}
        style={{ "--i": Math.min(index, 40) } as React.CSSProperties}
      >
        {text.slice(mark.start, mark.end)}
      </mark>,
    );
    at = mark.end;
  });
  if (at < text.length) parts.push(text.slice(at));
  return <>{parts}</>;
}
