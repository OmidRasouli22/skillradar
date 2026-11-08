"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { CvMethod } from "@/components/cv/CvMethod";
import { CvResults } from "@/components/cv/CvResults";
import { CvSource } from "@/components/cv/CvSource";
import { ProfileEditor } from "@/components/cv/ProfileEditor";
import { ShowcasePanel } from "@/components/cv/ShowcasePanel";
import { JobDialog, type Origin } from "@/components/JobDialog";
import { getOverview, type Overview } from "@/lib/api";
import {
  analyse,
  getShowcase,
  getShowcases,
  getStatus,
  readCv,
  type Analysis,
  type CvProfile,
  type CvStatus,
  type Showcase,
  type ShowcaseItem,
} from "@/lib/cv";
import { count, day } from "@/lib/format";

// Wait this long after the last edit before comparing again.
const DEBOUNCE_MS = 300;

type Result = { key: string; data?: Analysis; error?: string };

// The CV analysis page (local only): read a CV, check the profile, compare it with
// the open postings and see what to learn next.
export function CvAnalyser() {
  const [status, setStatus] = useState<CvStatus | null>(null);
  const [overview, setOverview] = useState<Overview | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [showcases, setShowcases] = useState<ShowcaseItem[]>([]);

  const [text, setText] = useState("");
  const [from, setFrom] = useState("");
  const [reading, setReading] = useState<"claude" | "keywords" | null>(null);
  const [readError, setReadError] = useState<string | null>(null);
  const [showcase, setShowcase] = useState<Showcase | null>(null);
  const [edited, setEdited] = useState(false);

  const [profile, setProfile] = useState<CvProfile | null>(null);
  const [notes, setNotes] = useState<string[]>([]);
  const [source, setSource] = useState("");
  const [role, setRole] = useState("all");
  const [region, setRegion] = useState("all");
  const [result, setResult] = useState<Result | null>(null);
  const [job, setJob] = useState<{ refnr: string; origin: Origin } | null>(null);
  const profileRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    Promise.all([getStatus(), getOverview(), getShowcases()])
      .then(([s, o, list]) => {
        setStatus(s);
        setOverview(o);
        setShowcases(list);
      })
      .catch((error: Error) => setLoadError(error.message));
  }, []);

  const key = profile ? JSON.stringify([profile, role, region]) : null;

  useEffect(() => {
    if (!profile || !key) return;
    const controller = new AbortController();
    const timer = window.setTimeout(() => {
      analyse(profile, role, region, controller.signal)
        .then((data) => setResult({ key, data }))
        .catch((error: Error) => {
          if (error.name !== "AbortError") setResult({ key, error: error.message });
        });
    }, DEBOUNCE_MS);
    return () => {
      window.clearTimeout(timer);
      controller.abort();
    };
  }, [key, profile, role, region]);

  function show(next: CvProfile, nextNotes: string[], label: string) {
    setProfile(next);
    setNotes(nextNotes);
    setSource(label);
    setResult(null);
    window.requestAnimationFrame(() => profileRef.current?.scrollIntoView({ behavior: "smooth", block: "start" }));
  }

  async function read(mode: "claude" | "keywords") {
    setReading(mode);
    setReadError(null);
    try {
      const answer = await readCv(text, mode);
      setShowcase(null);
      setEdited(false);
      if (answer.profile.role && status?.roles.some((r) => r.id === answer.profile.role)) setRole(answer.profile.role);
      const label =
        mode === "claude" ? `read by ${status?.model ?? "Claude"} for $${answer.cost_usd.toFixed(4)}` : "quick keyword read";
      show(answer.profile, answer.notes, label);
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
      setFrom(`example: ${example.title}`);
      setShowcase(example);
      setEdited(false);
      setRole(example.target.role);
      setRegion(example.target.region);
      if (example.profile) show(example.profile, example.notes, "the example's saved reading");
      else setReadError("This example has no saved reading yet: run skillradar-cv showcase --refresh.");
    } catch (error) {
      setReadError((error as Error).message);
    }
  }

  const current = result?.key === key ? result : null;
  const shown = current?.data ?? result?.data ?? null;
  const roles = status?.roles ?? [];
  const regions = status?.regions ?? [];

  return (
    <main className="page cv">
      <header className="top">
        <Link className="brand" href="/">
          Skill<span>Radar</span>
        </Link>
        <nav className="cv-nav" aria-label="Pages">
          <Link href="/">Dashboard</Link>
          <Link href="/cv" aria-current="page">
            CV analysis
          </Link>
          <Link href="/health">Health</Link>
        </nav>
      </header>

      <section className="hero">
        <h1>How well does your CV fit the job market?</h1>
        <p>
          Compare your CV with{" "}
          <strong>{overview ? `${count(overview.tech_postings)} open tech postings` : "the open tech postings"}</strong>
          {overview?.as_of ? ` from ${day(overview.as_of)}` : ""}: where you fit, which jobs match, and which skill would open
          the most doors. Runs on this computer only.
        </p>
      </section>

      {loadError ? (
        <div className="card">
          <div className="state" role="alert">
            <strong>The CV analysis is not available.</strong>
            {loadError}
          </div>
        </div>
      ) : (
        <>
          <CvSource
            status={status}
            text={text}
            onText={(value, label) => {
              setText(value);
              setFrom(label);
            }}
            showcases={showcases}
            example={showcase?.id ?? null}
            onExample={loadExample}
            onRead={read}
            reading={reading}
            error={readError}
          />

          <div ref={profileRef} className="cv-anchor">
            {profile && status && (
              <ProfileEditor
                profile={profile}
                onChange={(next) => {
                  setProfile(next);
                  setEdited(true);
                }}
                notes={notes}
                skillNames={status.skills}
                roles={roles.filter((r) => r.id !== "all")}
                from={source || from}
              />
            )}
          </div>

          {profile && showcase && <ShowcasePanel showcase={showcase} edited={edited} />}

          {profile && (
            <section className="cv-step cv-compare" aria-labelledby="cv-compare-title">
              <div className="cv-compare-head">
                <span className="cv-step-number">3</span>
                <h2 id="cv-compare-title">Compare with the postings</h2>
              </div>
              <div className="filters" role="search" aria-label="Postings to compare with">
                <label className="field">
                  <span className="sr-only">Role</span>
                  <select value={role} onChange={(event) => setRole(event.target.value)} aria-label="Role">
                    {roles.map((r) => (
                      <option key={r.id} value={r.id}>
                        {r.label}
                      </option>
                    ))}
                  </select>
                </label>
                <label className="field">
                  <span className="sr-only">Region</span>
                  <select value={region} onChange={(event) => setRegion(event.target.value)} aria-label="Region">
                    {regions.map((r) => (
                      <option key={r.id} value={r.id}>
                        {r.label}
                      </option>
                    ))}
                  </select>
                </label>
              </div>
              {current?.error ? (
                <div className="card">
                  <div className="state" role="alert">
                    <strong>The comparison failed.</strong>
                    {current.error}
                  </div>
                </div>
              ) : shown ? (
                <CvResults
                  analysis={shown}
                  loading={!current}
                  onRole={setRole}
                  onOpen={(refnr, origin) => setJob({ refnr, origin })}
                />
              ) : (
                <div className="card">
                  <div className="state">Comparing with the postings…</div>
                </div>
              )}
            </section>
          )}

          {job && <JobDialog key={job.refnr} refnr={job.refnr} origin={job.origin} onClose={() => setJob(null)} />}
          <CvMethod />
        </>
      )}
    </main>
  );
}
