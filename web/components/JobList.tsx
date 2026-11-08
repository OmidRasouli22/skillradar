"use client";

import { useEffect, useState } from "react";
import { getPostings, type PostingCard } from "@/lib/api";
import { band } from "@/lib/cv";
import { count, day, percent } from "@/lib/format";
import { label, REMOTE, SENIORITY } from "@/lib/labels";
import type { Origin } from "./JobDialog";

type Page = { key: string; items: PostingCard[]; total: number; error?: string };

// The open postings for the current role and region, newest first, 20 at a time.
export function JobList(props: {
  role: string;
  region: string;
  title: string;
  active: string | null;
  onOpen: (refnr: string, origin: Origin) => void;
  // How well the CV matches each posting, when a CV is loaded (local page only).
  scores?: Record<string, number>;
}) {
  const { role, region, title, active, onOpen, scores } = props;
  const key = `${role}|${region}`;
  const [page, setPage] = useState<Page | null>(null);
  const [offset, setOffset] = useState<{ key: string; value: number }>({ key, value: 0 });
  const wanted = offset.key === key ? offset.value : 0;

  useEffect(() => {
    const controller = new AbortController();
    getPostings(role, region, wanted, controller.signal)
      .then((data) =>
        setPage((old) => ({
          key,
          total: data.total,
          // More of the same list is added below; a new filter starts a new list.
          items: wanted > 0 && old?.key === key ? [...old.items, ...data.items] : data.items,
        })),
      )
      .catch((error: Error) => {
        if (error.name !== "AbortError") setPage({ key, items: [], total: 0, error: error.message });
      });
    return () => controller.abort();
  }, [role, region, wanted, key]);

  const current = page?.key === key ? page : null;
  return (
    <aside className="sidebar" aria-labelledby="jobs-title">
      <div className="sidebar-head">
        <h2 id="jobs-title">Open jobs</h2>
        <p>{current ? `${count(current.total)} ${title}` : "Loading…"}</p>
      </div>
      {current?.error ? (
        <div className="state" role="alert">
          {current.error}
        </div>
      ) : (
        <ul className={current ? "jobs" : "jobs loading"} key={key}>
          {(current?.items ?? []).map((job, index) => (
            <li key={job.refnr} style={{ "--i": Math.min(index % 20, 12) } as React.CSSProperties}>
              <button
                type="button"
                className={job.refnr === active ? "job active" : "job"}
                onClick={(event) => {
                  const box = event.currentTarget.getBoundingClientRect();
                  onOpen(job.refnr, { x: box.left, y: box.top, width: box.width, height: box.height });
                }}
              >
                {scores && (
                  <span
                    className={`job-match ${scores[job.refnr] === undefined ? "none" : band(scores[job.refnr])}`}
                    title={scores[job.refnr] === undefined ? "Names too few skills to compare" : "How well your CV matches"}
                  >
                    {scores[job.refnr] === undefined ? "–" : percent(scores[job.refnr])}
                  </span>
                )}
                <span className="job-title">{job.title}</span>
                <span className="job-meta">
                  {[job.employer, job.city].filter(Boolean).join(" · ")}
                </span>
                <span className="job-tags">
                  <span className="tag">{label(SENIORITY, job.seniority)}</span>
                  {job.remote !== "unknown" && <span className="tag">{label(REMOTE, job.remote)}</span>}
                  {job.published && <span className="tag quiet">{day(job.published, false)}</span>}
                </span>
                {job.skills.length > 0 && <span className="job-skills">{job.skills.join(" · ")}</span>}
              </button>
            </li>
          ))}
        </ul>
      )}
      {current && current.items.length < current.total && (
        <button
          type="button"
          className="more"
          onClick={() => setOffset({ key, value: current.items.length })}
        >
          Show more
        </button>
      )}
    </aside>
  );
}
