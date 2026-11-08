"use client";

import { useState } from "react";
import { EVIDENCE, LEVELS, SENIORITY, type Choice, type CvProfile, type CvSkill, type Evidence, type Level } from "@/lib/cv";

const MAX_SKILLS = 150;

// What was read from the CV. Everything can be corrected; the comparison updates as
// you edit.
export function ProfileEditor(props: {
  profile: CvProfile;
  onChange: (profile: CvProfile) => void;
  notes: string[];
  skillNames: string[];
  roles: Choice[];
  from: string;
}) {
  const { profile, onChange, notes, skillNames, roles, from } = props;
  const [name, setName] = useState("");
  const [evidence, setEvidence] = useState<Evidence>("work");
  const [addError, setAddError] = useState<string | null>(null);

  const update = (part: Partial<CvProfile>) => onChange({ ...profile, ...part });
  const level = (language: string) => profile.languages.find((l) => l.language === language)?.level ?? "";
  const others = profile.languages.filter((l) => l.language !== "German" && l.language !== "English");

  function setLevel(language: string, value: Level | "") {
    const rest = profile.languages.filter((l) => l.language !== language);
    update({ languages: value ? [...rest, { language, level: value }] : rest });
  }

  function setSkill(index: number, skill: CvSkill | null) {
    const skills = [...profile.skills];
    if (skill) skills[index] = skill;
    else skills.splice(index, 1);
    update({ skills });
  }

  function add() {
    const wanted = name.trim().replace(/\s+/g, " ");
    if (!wanted) return;
    // Use the list's spelling when the name is in the list.
    const known = skillNames.find((s) => s.toLowerCase() === wanted.toLowerCase()) ?? wanted;
    if (profile.skills.some((s) => s.name.toLowerCase() === known.toLowerCase())) {
      setAddError(`${known} is already in your profile.`);
      return;
    }
    if (known.length > 80 || profile.skills.length >= MAX_SKILLS) {
      setAddError(known.length > 80 ? "That name is too long." : `At most ${MAX_SKILLS} skills.`);
      return;
    }
    update({
      skills: [...profile.skills, { name: known, evidence, years: null, last_used: null, context: "", source: "you" }],
    });
    setName("");
    setAddError(null);
  }

  return (
    <div className="cv-profile">
      <p className="cv-muted">
        Read from your CV ({from}). Fix anything that is wrong: every number above updates as you edit.
      </p>

      {notes.length > 0 && (
        <ul className="cv-notes">
          {notes.map((note) => (
            <li key={note}>{note}</li>
          ))}
        </ul>
      )}

      <div className="cv-fields">
        <label className="cv-field">
          <span>Current title</span>
          <input
            value={profile.headline}
            maxLength={120}
            onChange={(event) => update({ headline: event.target.value })}
            placeholder="e.g. Data Engineer"
          />
        </label>
        <label className="cv-field">
          <span>Closest role</span>
          <select value={profile.role} onChange={(event) => update({ role: event.target.value })}>
            {roles.map((role) => (
              <option key={role.id} value={role.id}>
                {role.label}
              </option>
            ))}
          </select>
        </label>
        <label className="cv-field">
          <span>Seniority</span>
          <select value={profile.seniority} onChange={(event) => update({ seniority: event.target.value })}>
            {SENIORITY.map((s) => (
              <option key={s.value} value={s.value}>
                {s.label}
              </option>
            ))}
          </select>
        </label>
        <label className="cv-field">
          <span>Years in IT work</span>
          <input
            type="number"
            min={0}
            max={60}
            step={0.5}
            value={profile.years_experience ?? ""}
            onChange={(event) => {
              const value = event.target.value === "" ? null : Number(event.target.value);
              update({ years_experience: value === null || (value >= 0 && value <= 60) ? value : profile.years_experience });
            }}
          />
        </label>
        <label className="cv-field">
          <span>German</span>
          <select value={level("German")} onChange={(event) => setLevel("German", event.target.value as Level | "")}>
            {LEVELS.map((l) => (
              <option key={l.value} value={l.value}>
                {l.label}
              </option>
            ))}
          </select>
        </label>
        <label className="cv-field">
          <span>English</span>
          <select value={level("English")} onChange={(event) => setLevel("English", event.target.value as Level | "")}>
            {LEVELS.map((l) => (
              <option key={l.value} value={l.value}>
                {l.label}
              </option>
            ))}
          </select>
        </label>
      </div>
      {others.length > 0 && (
        <p className="cv-muted">
          Also speaks: {others.map((l) => `${l.language === "Other" ? "another language" : l.language} (${l.level})`).join(", ")}.
          Postings here only ask for German and English.
        </p>
      )}

      <div className="cv-skills">
        <div className="cv-skills-head">
          <h3>
            Skills <small>{profile.skills.length}</small>
          </h3>
          <span className="cv-muted">How a skill shows on the CV decides how much it counts.</span>
        </div>
        {EVIDENCE.map((group) => {
          const items = profile.skills
            .map((skill, index) => ({ skill, index }))
            .filter(({ skill }) => skill.evidence === group.value)
            .sort((a, b) => a.skill.name.localeCompare(b.skill.name));
          return (
            <div className={`cv-skill-group ${group.value}`} key={group.value}>
              <div className="cv-skill-group-label">
                {group.label} <small>{group.hint}</small>
              </div>
              {items.length === 0 ? (
                <span className="cv-muted">none</span>
              ) : (
                <ul>
                  {items.map(({ skill, index }) => (
                    <li key={`${skill.name}-${index}`} title={describe(skill)}>
                      <span className="cv-chip-name">{skill.name}</span>
                      {skill.source === "keyword" && (
                        <span className="cv-chip-source" title="Found by keyword search; Claude did not name it">
                          kw
                        </span>
                      )}
                      <select
                        aria-label={`How ${skill.name} shows on the CV`}
                        value={skill.evidence}
                        onChange={(event) => setSkill(index, { ...skill, evidence: event.target.value as Evidence })}
                      >
                        {EVIDENCE.map((e) => (
                          <option key={e.value} value={e.value}>
                            {e.label}
                          </option>
                        ))}
                      </select>
                      <button type="button" className="cv-chip-remove" aria-label={`Remove ${skill.name}`} onClick={() => setSkill(index, null)}>
                        ×
                      </button>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          );
        })}
        <form
          className="cv-add"
          onSubmit={(event) => {
            event.preventDefault();
            add();
          }}
        >
          <input
            list="cv-skill-names"
            value={name}
            maxLength={80}
            placeholder="Add a skill"
            aria-label="Skill to add"
            onChange={(event) => setName(event.target.value)}
          />
          <datalist id="cv-skill-names">
            {skillNames.map((s) => (
              <option key={s} value={s} />
            ))}
          </datalist>
          <select aria-label="How the new skill shows on the CV" value={evidence} onChange={(event) => setEvidence(event.target.value as Evidence)}>
            {EVIDENCE.map((e) => (
              <option key={e.value} value={e.value}>
                {e.label}
              </option>
            ))}
          </select>
          <button type="submit" className="toggle">
            Add
          </button>
        </form>
        {addError && <p className="cv-hint warn">{addError}</p>}
      </div>
    </div>
  );
}

function describe(skill: CvSkill): string {
  const parts = [skill.context, skill.years ? `about ${skill.years} years` : "", skill.last_used ? `last used ${skill.last_used}` : ""];
  return parts.filter(Boolean).join(" · ") || skill.name;
}
