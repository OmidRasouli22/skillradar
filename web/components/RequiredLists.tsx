"use client";

import type { Skill } from "@/lib/api";
import { count, percent } from "@/lib/format";
import { useTip } from "./Tooltip";

// Skills asked for often enough to compare, split by how often the posting requires them.
export function RequiredLists({ must, bonus }: { must: Skill[]; bonus: Skill[] }) {
  return (
    <div className="split">
      <List title="Most often required" skills={must} />
      <List title="Least often required" skills={bonus} />
    </div>
  );
}

function List({ title, skills }: { title: string; skills: Skill[] }) {
  const tip = useTip();
  return (
    <div>
      <h3 className="mini-title">{title}</h3>
      <ul className="meters">
        {skills.map((skill) => {
          const ratio = skill.required_postings / skill.postings;
          return (
            <li
              key={skill.name}
              {...tip({
                value: `${percent(ratio)} required`,
                label: skill.name,
                detail: `required in ${count(skill.required_postings)} of ${count(skill.postings)} postings that ask for it`,
              })}
            >
              <span className="name">{skill.name}</span>
              <span className="meter" aria-hidden="true">
                <span style={{ width: `${ratio * 100}%` }} />
              </span>
              <span className="value">{percent(ratio)}</span>
            </li>
          );
        })}
      </ul>
    </div>
  );
}
