"use client";

import type { Skill } from "@/lib/api";
import { count, percent } from "@/lib/format";
import { useTip } from "./Tooltip";

// Ranked bars: the whole bar is "asks for it", the dark part is "requires it".
export function SkillBars({ skills, total }: { skills: Skill[]; total: number }) {
  const tip = useTip();
  return (
    <ol className="bars">
      {skills.map((skill, index) => (
        <li
          key={skill.name}
          className="bar-row"
          {...tip({
            value: percent(skill.share),
            label: skill.name,
            detail: `${count(skill.postings)} of ${count(total)} postings · required in ${count(skill.required_postings)}`,
          })}
        >
          <span className="rank">{index + 1}</span>
          <span className="name">{skill.name}</span>
          <span className="track" aria-hidden="true">
            <span className="fill nice" style={{ width: `${skill.share * 100}%` }} />
            <span className="fill required" style={{ width: `${skill.required_share * 100}%` }} />
          </span>
          <span className="value">{percent(skill.share)}</span>
        </li>
      ))}
    </ol>
  );
}
