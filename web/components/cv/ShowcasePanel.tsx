"use client";

import { useEffect, useState } from "react";
import { getShowcaseChecks, type CheckResult, type Showcase } from "@/lib/cv";
import { day } from "@/lib/format";

// For an example CV: what a person reading it expects, why, and whether the analysis
// agrees. The checks use the saved reading, not edits made on this page.
export function ShowcasePanel({ showcase, edited }: { showcase: Showcase; edited: boolean }) {
  const [state, setState] = useState<{ id: string; results?: CheckResult[]; asOf?: string | null; error?: string } | null>(
    null,
  );

  useEffect(() => {
    let live = true;
    getShowcaseChecks(showcase.id)
      .then((body) => live && setState({ id: showcase.id, results: body.results, asOf: body.as_of }))
      .catch((error: Error) => live && setState({ id: showcase.id, error: error.message }));
    return () => {
      live = false;
    };
  }, [showcase.id]);

  const current = state?.id === showcase.id ? state : null;
  const results = current?.results ?? [];
  const passed = results.filter((r) => r.passed).length;

  return (
    <div className="cv-showcase">
      <div className="cv-showcase-head">
        <div>
          <h3>{showcase.title}</h3>
          <p className="cv-muted">
            {showcase.person}. {showcase.story}
          </p>
        </div>
        {current?.results && (
          <div className={`cv-tally ${passed === results.length ? "all" : "some"}`}>
            <strong>
              {passed} / {results.length}
            </strong>
            <span>checks pass</span>
          </div>
        )}
      </div>
      {edited && (
        <p className="cv-muted cv-small">
          You changed the profile. The checks below still use the saved reading; the results further down use your edits.
        </p>
      )}
      {current?.error && (
        <p className="note" role="alert">
          {current.error}
        </p>
      )}
      {!current && <p className="cv-muted">Running the checks…</p>}
      {results.length > 0 && (
        <div className="table-wrap">
          <table className="cv-checks">
            <thead>
              <tr>
                <th scope="col" className="sr-only">
                  Result
                </th>
                <th scope="col">Expected</th>
                <th scope="col">Why</th>
                <th scope="col">Analysis says</th>
              </tr>
            </thead>
            <tbody>
              {results.map((r, index) => (
                <tr key={index} className={r.passed ? "pass" : "fail"}>
                  <td aria-label={r.passed ? "passes" : "fails"}>{r.passed ? "✓" : "✗"}</td>
                  <td>{r.check}</td>
                  <td>{r.why}</td>
                  <td>{r.actual}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <p className="cv-muted cv-small">
        Read by {showcase.read.model ?? "Claude"} ({showcase.read.prompt_version}){" "}
        {showcase.read.read_at ? `on ${day(showcase.read.read_at.slice(0, 10))}` : ""}. Match checks use today&apos;s postings
        {current?.asOf ? ` (${day(current.asOf)})` : ""}, so they can change as the postings change.
      </p>
    </div>
  );
}
