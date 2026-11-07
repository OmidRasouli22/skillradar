"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { PostingText } from "@/components/PostingText";
import type { Mark } from "@/lib/api";
import {
  getLabelPosting,
  getMarks,
  getSample,
  saveLabel,
  type Answer,
  type LabelPosting,
  type Sample,
  type SkillItem,
  type Status,
} from "@/lib/labeling";

const EMPTY: Answer = { role: "", seniority: "", remote: "", languages: [], skills: [] };
const STATUS_TEXT: Record<Status, string> = { todo: "No label yet", draft: "Draft, not checked", verified: "Verified" };

// Check and correct one reference label at a time. The text shows where each skill of
// the label is written; Claude's answer is never shown, so it can't sway the label.
export function LabelTool() {
  const [sample, setSample] = useState<Sample | null>(null);
  const [refnr, setRefnr] = useState<string | null>(null);
  const [posting, setPosting] = useState<LabelPosting | null>(null);
  const [answer, setAnswer] = useState<Answer>(EMPTY);
  const [note, setNote] = useState("");
  const [dirty, setDirty] = useState(false);
  const [marks, setMarks] = useState<Mark[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [newSkill, setNewSkill] = useState("");

  useEffect(() => {
    getSample()
      .then((data) => {
        setSample(data);
        const asked = new URLSearchParams(window.location.search).get("refnr");
        const known = data.items.find((item) => item.refnr === asked);
        const next = known ?? data.items.find((item) => item.status !== "verified") ?? data.items[0];
        setRefnr(next?.refnr ?? null);
      })
      .catch((e: Error) => setError(e.message));
  }, []);

  useEffect(() => {
    if (!refnr) return;
    let live = true;
    getLabelPosting(refnr)
      .then((data) => {
        if (!live) return;
        setPosting(data);
        setAnswer(data.label.answer ?? EMPTY);
        setNote(data.label.note);
        setDirty(false);
        setError(null);
        window.history.replaceState(null, "", `?refnr=${encodeURIComponent(refnr)}`);
      })
      .catch((e: Error) => live && setError(e.message));
    return () => {
      live = false;
    };
  }, [refnr]);

  // Marks follow the label's skills, a moment after the last change.
  useEffect(() => {
    if (!posting) return;
    const controller = new AbortController();
    const timer = setTimeout(() => {
      getMarks(posting.refnr, answer.skills, controller.signal)
        .then((data) => setMarks(data.marks))
        .catch(() => undefined);
    }, 200);
    return () => {
      clearTimeout(timer);
      controller.abort();
    };
  }, [posting, answer.skills]);

  const update = useCallback((change: Partial<Answer>) => {
    setAnswer((old) => ({ ...old, ...change }));
    setDirty(true);
  }, []);

  const index = sample?.items.findIndex((item) => item.refnr === refnr) ?? -1;
  const counts = useMemo(() => {
    const result = { todo: 0, draft: 0, verified: 0 };
    sample?.items.forEach((item) => (result[item.status] += 1));
    return result;
  }, [sample]);
  const marked = useMemo(() => new Set(marks.filter((m) => m.kind === "required" || m.kind === "nice").map((m) => m.label.toLowerCase())), [marks]);
  const complete = Boolean(answer.role && answer.seniority && answer.remote);

  function go(next: string | undefined) {
    if (!next || next === refnr) return;
    if (dirty && !window.confirm("This label has changes that are not saved. Leave anyway?")) return;
    setRefnr(next);
  }

  function nextOpen(from: number): string | undefined {
    const items = sample?.items ?? [];
    for (let i = 1; i <= items.length; i++) {
      const item = items[(from + i) % items.length];
      if (item.status !== "verified") return item.refnr;
    }
    return undefined;
  }

  async function save(status: "draft" | "verified") {
    if (!posting || saving) return;
    setSaving(true);
    try {
      const saved = await saveLabel(posting.refnr, answer, status, note);
      setDirty(false);
      setError(null);
      setSample((old) =>
        old && {
          ...old,
          items: old.items.map((item) => (item.refnr === saved.refnr ? { ...item, status: saved.status } : item)),
        },
      );
      setPosting((old) => old && { ...old, label: saved });
      if (status === "verified") {
        const next = nextOpen(index);
        if (next && next !== saved.refnr) setRefnr(next);
      }
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setSaving(false);
    }
  }

  // Cmd/Ctrl + Enter: verify and go to the next label to check.
  const saveRef = useRef(save);
  useEffect(() => {
    saveRef.current = save;
  });
  useEffect(() => {
    function onKey(event: KeyboardEvent) {
      if ((event.metaKey || event.ctrlKey) && event.key === "Enter") {
        event.preventDefault();
        void saveRef.current("verified");
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  function addSkill() {
    const name = newSkill.trim().replace(/\s+/g, " ");
    if (!name) return;
    const known = sample?.skills.find((s) => s.toLowerCase() === name.toLowerCase()) ?? name;
    if (!answer.skills.some((s) => s.name.toLowerCase() === known.toLowerCase())) {
      update({ skills: [...answer.skills, { name: known, required: true }] });
    }
    setNewSkill("");
  }

  function setSkill(position: number, change: Partial<SkillItem> | null) {
    const skills = answer.skills.flatMap((skill, i) => (i !== position ? [skill] : change ? [{ ...skill, ...change }] : []));
    update({ skills });
  }

  if (error && !sample) {
    return (
      <main className="page">
        <div className="card state" role="alert">
          <strong>The labels are not available.</strong>
          {error}
        </div>
      </main>
    );
  }

  const role = sample?.choices.role.find((r) => r.id === answer.role);
  // While the next posting loads, the old one is not shown.
  const shown = posting?.refnr === refnr ? posting : null;

  return (
    <main className="page review">
      <header className="top">
        <div className="brand">
          Skill<span>Radar</span> · labels
        </div>
        {sample && (
          <div>
            {counts.verified} of {sample.items.length} verified · {counts.draft} drafts · {counts.todo} without label
          </div>
        )}
      </header>

      {sample && (
        <div className="review-progress" aria-hidden="true">
          <span style={{ width: `${(100 * counts.verified) / Math.max(sample.items.length, 1)}%` }} />
        </div>
      )}

      <nav className="review-nav" aria-label="Choose a posting">
        <button type="button" className="toggle" onClick={() => go(sample?.items[index - 1]?.refnr)} disabled={index <= 0}>
          ← Back
        </button>
        <select
          aria-label="Posting"
          value={refnr ?? ""}
          onChange={(event) => go(event.target.value)}
        >
          {sample?.items.map((item, i) => (
            <option key={item.refnr} value={item.refnr}>
              {i + 1}. {item.status === "verified" ? "✓" : item.status === "draft" ? "•" : "○"} {item.title ?? item.refnr}
            </option>
          ))}
        </select>
        <button
          type="button"
          className="toggle"
          onClick={() => go(sample?.items[index + 1]?.refnr)}
          disabled={!sample || index >= sample.items.length - 1}
        >
          Next →
        </button>
      </nav>

      <div className="review-layout">
        <section className="card review-text" aria-busy={!shown}>
          {shown ? (
            <>
              <div className="card-head">
                <div>
                  <h2>{shown.title || "Job posting"}</h2>
                  <p>
                    <a href={`https://www.arbeitsagentur.de/jobsuche/jobdetail/${encodeURIComponent(shown.refnr)}`} target="_blank" rel="noreferrer">
                      {shown.refnr}
                    </a>
                  </p>
                </div>
              </div>
              <PostingText text={shown.text} marks={marks} still />
            </>
          ) : (
            <div className="state">Loading…</div>
          )}
        </section>

        <aside className="card review-form">
          {shown && sample && (
            <form
              onSubmit={(event) => {
                event.preventDefault();
                void save("verified");
              }}
            >
              <div className={`review-status ${shown.label.status}`}>
                {STATUS_TEXT[shown.label.status]}
                {shown.label.drafted_by && shown.label.status !== "todo" && <span> · drafted by {shown.label.drafted_by}</span>}
                {dirty && <span> · changed</span>}
              </div>

              <div className="field">
                <label htmlFor="role">Role</label>
                <select id="role" value={answer.role} onChange={(e) => update({ role: e.target.value })}>
                  <option value="" disabled>
                    Choose…
                  </option>
                  {sample.choices.role.map((r) => (
                    <option key={r.id} value={r.id}>
                      {r.id}
                    </option>
                  ))}
                </select>
                {role && <small>{role.hint}</small>}
              </div>

              <div className="review-pair">
                <Choice id="seniority" label="Seniority" value={answer.seniority} options={sample.choices.seniority} onChange={(v) => update({ seniority: v })} />
                <Choice id="remote" label="Home office" value={answer.remote} options={sample.choices.remote} onChange={(v) => update({ remote: v })} />
              </div>

              <fieldset className="review-group">
                <legend>Languages</legend>
                {answer.languages.map((item, i) => (
                  <div className="review-pair with-remove" key={i}>
                    <select
                      aria-label="Language"
                      value={item.language}
                      onChange={(e) => update({ languages: answer.languages.map((l, j) => (j === i ? { ...l, language: e.target.value } : l)) })}
                    >
                      {sample.choices.language.map((l) => (
                        <option key={l}>{l}</option>
                      ))}
                    </select>
                    <select
                      aria-label="Level"
                      value={item.level}
                      onChange={(e) => update({ languages: answer.languages.map((l, j) => (j === i ? { ...l, level: e.target.value } : l)) })}
                    >
                      {sample.choices.level.map((l) => (
                        <option key={l}>{l}</option>
                      ))}
                    </select>
                    <button type="button" className="remove" aria-label={`Remove ${item.language}`} onClick={() => update({ languages: answer.languages.filter((_, j) => j !== i) })}>
                      ×
                    </button>
                  </div>
                ))}
                <button type="button" className="toggle" onClick={() => update({ languages: [...answer.languages, { language: "German", level: "unknown" }] })}>
                  + Language
                </button>
              </fieldset>

              <fieldset className="review-group">
                <legend>
                  Skills <small>click to switch required / nice to have</small>
                </legend>
                <ul className="review-skills">
                  {answer.skills.map((skill, i) => (
                    <li key={`${i}-${skill.name}`} className={skill.required ? "required" : "nice"}>
                      <button type="button" onClick={() => setSkill(i, { required: !skill.required })} title="Switch required / nice to have">
                        {skill.name}
                        <em>{skill.required ? "required" : "nice"}</em>
                        {!marked.has(skill.name.toLowerCase()) && <i title="Not found in the text">not in text</i>}
                      </button>
                      <button type="button" className="remove" aria-label={`Remove ${skill.name}`} onClick={() => setSkill(i, null)}>
                        ×
                      </button>
                    </li>
                  ))}
                </ul>
                <div className="review-add">
                  <input
                    list="skill-names"
                    value={newSkill}
                    placeholder="Add a skill"
                    aria-label="Add a skill"
                    maxLength={80}
                    onChange={(e) => setNewSkill(e.target.value)}
                    onKeyDown={(e) => {
                      if (e.key === "Enter" && !e.metaKey && !e.ctrlKey) {
                        e.preventDefault();
                        addSkill();
                      }
                    }}
                  />
                  <button type="button" className="toggle" onClick={addSkill}>
                    Add
                  </button>
                  <datalist id="skill-names">
                    {sample.skills.map((name) => (
                      <option key={name} value={name} />
                    ))}
                  </datalist>
                </div>
              </fieldset>

              <div className="field">
                <label htmlFor="note">Note</label>
                <textarea id="note" rows={2} maxLength={1000} value={note} onChange={(e) => {
                    setNote(e.target.value);
                    setDirty(true);
                  }} />
              </div>

              {error && (
                <div className="review-error" role="alert">
                  {error}
                </div>
              )}

              <div className="review-actions">
                <button type="submit" className="button" disabled={!complete || saving}>
                  Verify and next
                </button>
                <button type="button" className="toggle" disabled={!complete || saving} onClick={() => void save("draft")}>
                  Save draft
                </button>
              </div>
              <p className="review-hint">⌘ / Ctrl + Enter verifies. Rules: eval/GUIDE.md</p>
            </form>
          )}
        </aside>
      </div>
    </main>
  );
}

function Choice(props: { id: string; label: string; value: string; options: string[]; onChange: (value: string) => void }) {
  return (
    <div className="field">
      <label htmlFor={props.id}>{props.label}</label>
      <select id={props.id} value={props.value} onChange={(e) => props.onChange(e.target.value)}>
        <option value="" disabled>
          Choose…
        </option>
        {props.options.map((option) => (
          <option key={option}>{option}</option>
        ))}
      </select>
    </div>
  );
}
